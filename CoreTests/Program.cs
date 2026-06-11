using System.IO;
using AcbStudio.Core;

// Round-trip tests for the ACB Studio core:
//   1. AFS2 build/parse round-trip incl. the KI-001 aligned-header repro
//   2. @UTF parse -> serialize -> parse equality (nested tables, constants)
//   3. WAV -> HCA -> WAV with a PSNR gate (same 40 dB bar as the original tool)
//   4. Full synthetic inject: resample + loop + AWB rebuild + ACB patch

int failures = 0;
string dir = Path.Combine(Path.GetTempPath(), "acb_core_test_" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(dir);

void Check(bool condition, string what)
{
    if (condition)
    {
        Console.WriteLine($"  OK   {what}");
    }
    else
    {
        Console.WriteLine($"  FAIL {what}");
        failures++;
    }
}

try
{
    // ── 1. AFS2 / KI-001 ─────────────────────────────────────────────────────
    Console.WriteLine("AFS2:");

    // KI-001 minimal repro: 2 files, id_intsize=2, offset_intsize=4, align=32
    // -> header = 16 + 2*2 + 4*3 = 32 bytes, exactly aligned. Upstream's bug
    // shifted every offset by one alignment block in this case.
    var payload = new byte[64];
    payload[0] = (byte)'H'; payload[1] = (byte)'C'; payload[2] = (byte)'A'; payload[3] = 0;
    for (int i = 4; i < payload.Length; i++) payload[i] = 0xAA;

    var ki001 = Afs2Archive.Parse(Afs2Archive.Build([payload, payload]));
    Check(ki001.FileCount == 2, "KI-001 repro: 2 files");
    Check(ki001.GetFileAt(0).AsSpan(0, 4).SequenceEqual("HCA\0"u8), "KI-001 repro: file 0 starts with HCA magic");
    Check(ki001.GetFileAt(1).AsSpan(0, 4).SequenceEqual("HCA\0"u8), "KI-001 repro: file 1 starts with HCA magic (upstream bug returned garbage)");

    // Round-trip at trigger and non-trigger file counts, with ragged sizes.
    foreach (int n in new[] { 1, 2, 3, 5, 10, 13 })
    {
        var blobs = new List<byte[]>();
        for (int i = 0; i < n; i++)
        {
            var b = new byte[37 + i * 13]; // deliberately not align-multiples
            for (int j = 0; j < b.Length; j++) b[j] = (byte)(i * 31 + j);
            blobs.Add(b);
        }
        var arc = Afs2Archive.Parse(Afs2Archive.Build(blobs));
        bool allMatch = arc.FileCount == n;
        for (int i = 0; i < n && allMatch; i++)
        {
            // Reader returns the aligned slot; compare the meaningful prefix.
            var got = arc.GetFileAt(i);
            allMatch = got.Length >= blobs[i].Length && got.AsSpan(0, blobs[i].Length).SequenceEqual(blobs[i]);
        }
        Check(allMatch, $"round-trip with {n} ragged blobs");
    }

    // ── 2. @UTF round-trip ───────────────────────────────────────────────────
    Console.WriteLine("@UTF:");

    var waveformTable = new UtfTable { Name = "Waveform" };
    waveformTable.Columns = ["Id", "EncodeType", "Streaming", "NumChannels", "SamplingRate", "NumSamples", "LoopFlag"];
    for (int i = 0; i < 3; i++)
    {
        waveformTable.Rows.Add(new Dictionary<string, UtfValue>
        {
            ["Id"] = new(UtfType.U16, (ushort)i),
            ["EncodeType"] = new(UtfType.U8, (byte)2),          // constant across rows
            ["Streaming"] = new(UtfType.U8, (byte)0),           // constant across rows
            ["NumChannels"] = new(UtfType.U8, (byte)(i == 2 ? 2 : 1)),
            ["SamplingRate"] = new(UtfType.U16, (ushort)44100),
            ["NumSamples"] = new(UtfType.U32, (uint)(44100 * (i + 1))),
            ["LoopFlag"] = new(UtfType.U8, (byte)(i == 1 ? 1 : 0)),
        });
    }

    var root = new UtfTable { Name = "Header" };
    root.Columns = ["Name", "AcbGuid", "WaveformTable"];
    root.Rows.Add(new Dictionary<string, UtfValue>
    {
        ["Name"] = new(UtfType.Str, "testbank"),
        ["AcbGuid"] = new(UtfType.Bytes, Enumerable.Range(1, 16).Select(b => (byte)b).ToArray()),
        ["WaveformTable"] = new(UtfType.Bytes, waveformTable),
    });

    var reparsed = UtfTable.Parse(root.Serialize());
    Check(reparsed.Name == "Header", $"root table name round-trips (got '{reparsed.Name}')");
    Check(reparsed.Rows[0]["Name"].Value as string == "testbank", "string cell round-trips");
    Check(reparsed.Rows[0]["AcbGuid"].Value is byte[] g && g.Length == 16 && g[0] == 1 && g[15] == 16,
        "bytes cell round-trips");

    var nested = reparsed.NestedTable("WaveformTable");
    Check(nested is not null, "nested table re-parses");
    Check(nested!.Rows.Count == 3, $"nested table has 3 rows (got {nested.Rows.Count})");
    Check(nested.Rows[1]["LoopFlag"].AsInt() == 1, "per-row u8 round-trips");
    Check(nested.Rows[2]["NumChannels"].AsInt() == 2, "varying column stays per-row");
    Check(nested.Rows[0]["EncodeType"].AsInt() == 2 && nested.Rows[2]["EncodeType"].AsInt() == 2,
        "constant column survives storage-class inference");
    Check(nested.Rows[2]["NumSamples"].AsInt() == 44100 * 3, "u32 round-trips");

    // Double round-trip: serialize the reparsed table, parse again, compare.
    var reparsed2 = UtfTable.Parse(reparsed.Serialize());
    Check(reparsed2.NestedTable("WaveformTable")!.Rows[1]["LoopFlag"].AsInt() == 1, "second round-trip stable");

    // ── 3. HCA encode/decode + PSNR ─────────────────────────────────────────
    Console.WriteLine("HCA:");

    short[] MakeSine(int frames, int channels, int rate)
    {
        var samples = new short[frames * channels];
        for (int i = 0; i < frames; i++)
        {
            for (int c = 0; c < channels; c++)
            {
                double t = (double)i / rate;
                samples[i * channels + c] = (short)(Math.Sin(2 * Math.PI * 440 * t) * 12000);
            }
        }
        return samples;
    }

    const int rate = 44100;
    const int frames = 44100; // 1 second
    var sine = MakeSine(frames, 1, rate);
    var sineWav = WavUtil.BuildPcm16Wav(sine, 1, rate);

    var hca = HcaCodec.EncodeWavToHca(sineWav);
    var hcaMeta = HcaMeta.Parse(hca);
    Check(hcaMeta.Channels == 1, $"encoded HCA channel count (got {hcaMeta.Channels})");
    Check(hcaMeta.SampleRate == rate, $"encoded HCA sample rate (got {hcaMeta.SampleRate})");
    Check(!hcaMeta.HasLoop, "non-looping encode has no loop chunk");

    var hcaLooped = HcaCodec.EncodeWavToHca(sineWav, loopWholeFile: true);
    Check(HcaMeta.Parse(hcaLooped).HasLoop, "loop-preserving encode emits a loop chunk");

    var decodedWav = HcaCodec.DecodeToWav(hca);
    var decodedFmt = WavUtil.ReadFormat(decodedWav);
    Check(decodedFmt.SampleRate == rate && decodedFmt.Channels == 1, "decoded WAV format matches");

    double Psnr(short[] reference, byte[] wavBytes)
    {
        var fmt = WavUtil.ReadFormat(wavBytes);
        int n = Math.Min(reference.Length, fmt.SampleFrames * fmt.Channels);
        // locate data chunk
        int off = -1;
        for (int p = 12; p + 8 <= wavBytes.Length;)
        {
            int size = BitConverter.ToInt32(wavBytes, p + 4);
            if (wavBytes[p] == 'd' && wavBytes[p + 1] == 'a' && wavBytes[p + 2] == 't' && wavBytes[p + 3] == 'a')
            {
                off = p + 8;
                break;
            }
            p += 8 + size + (size & 1);
        }
        double mse = 0;
        for (int i = 0; i < n; i++)
        {
            double d = reference[i] - BitConverter.ToInt16(wavBytes, off + i * 2);
            mse += d * d;
        }
        mse /= n;
        return mse <= 0 ? 999 : 10 * Math.Log10(32767.0 * 32767.0 / mse);
    }

    double psnr = Psnr(sine, decodedWav);
    Check(psnr >= 40, $"WAV->HCA->WAV PSNR >= 40 dB (got {psnr:F1} dB)");

    // ── 4. Full synthetic inject ─────────────────────────────────────────────
    Console.WriteLine("Inject:");

    // Build a 3-waveform bank: HCA blobs in an AWB + matching ACB tables.
    var blobsForBank = new List<byte[]>();
    for (int i = 0; i < 3; i++)
    {
        var tone = MakeSine(rate / 2, 1, rate);
        blobsForBank.Add(HcaCodec.EncodeWavToHca(WavUtil.BuildPcm16Wav(tone, 1, rate),
            loopWholeFile: i == 1)); // waveform 1 loops
    }

    var wfTable = new UtfTable { Name = "Waveform" };
    wfTable.Columns = ["Id", "EncodeType", "Streaming", "NumChannels", "SamplingRate", "NumSamples", "LoopFlag"];
    for (int i = 0; i < 3; i++)
    {
        var m = HcaMeta.Parse(blobsForBank[i]);
        wfTable.Rows.Add(new Dictionary<string, UtfValue>
        {
            ["Id"] = new(UtfType.U16, (ushort)i),
            ["EncodeType"] = new(UtfType.U8, (byte)2),
            ["Streaming"] = new(UtfType.U8, (byte)0),
            ["NumChannels"] = new(UtfType.U8, (byte)m.Channels),
            ["SamplingRate"] = new(UtfType.U16, (ushort)m.SampleRate),
            ["NumSamples"] = new(UtfType.U32, (uint)m.SampleCount),
            ["LoopFlag"] = new(UtfType.U8, (byte)(i == 1 ? 1 : 0)),
        });
    }

    var cueTable = new UtfTable { Name = "Cue" };
    cueTable.Columns = ["CueId", "ReferenceType", "ReferenceIndex", "Length"];
    for (int i = 0; i < 3; i++)
    {
        cueTable.Rows.Add(new Dictionary<string, UtfValue>
        {
            ["CueId"] = new(UtfType.U32, (uint)(100 + i)),
            ["ReferenceType"] = new(UtfType.U8, (byte)1),
            ["ReferenceIndex"] = new(UtfType.U16, (ushort)i),
            ["Length"] = new(UtfType.U32, (uint)500),
        });
    }

    var cueNameTable = new UtfTable { Name = "CueName" };
    cueNameTable.Columns = ["CueName", "CueIndex"];
    string[] names = ["door_open", "bgm_village", "leon_grunt"];
    for (int i = 0; i < 3; i++)
    {
        cueNameTable.Rows.Add(new Dictionary<string, UtfValue>
        {
            ["CueName"] = new(UtfType.Str, names[i]),
            ["CueIndex"] = new(UtfType.U16, (ushort)i),
        });
    }

    var acbRoot = new UtfTable { Name = "Header" };
    acbRoot.Columns = ["Name", "WaveformTable", "CueTable", "CueNameTable"];
    acbRoot.Rows.Add(new Dictionary<string, UtfValue>
    {
        ["Name"] = new(UtfType.Str, "synthbank"),
        ["WaveformTable"] = new(UtfType.Bytes, wfTable),
        ["CueTable"] = new(UtfType.Bytes, cueTable),
        ["CueNameTable"] = new(UtfType.Bytes, cueNameTable),
    });

    string acbPath = Path.Combine(dir, "synth.acb");
    string awbPath = Path.Combine(dir, "synth.awb");
    File.WriteAllBytes(acbPath, acbRoot.Serialize());
    File.WriteAllBytes(awbPath, Afs2Archive.Build(blobsForBank));

    var project = AcbProject.Open(acbPath);
    Check(project.Name == "synthbank", $"project opens (name '{project.Name}')");
    Check(project.Cues().Count == 3, "3 cues resolved");
    Check(project.Cues()[1].Name == "bgm_village", "cue names resolved");
    Check(project.Waveforms().Count == 3, "3 waveforms resolved");
    Check(project.Waveforms()[1].LoopFlag, "loop flag read from ACB");

    // Named extraction.
    var extracted = project.ExtractAllNamed(Path.Combine(dir, "named"));
    Check(extracted.Count == 3, $"named extraction wrote 3 files (got {extracted.Count})");
    Check(extracted.Any(p => Path.GetFileName(p) == "bgm_village.wav"), "cue-named output file exists");

    // Queue a replacement for waveform 1 (the looping one) at 22050 Hz
    // so the auto-resample path runs too.
    var replacementTone = MakeSine(22050 * 2, 1, 22050); // 2 seconds @ 22050
    string replacementWav = Path.Combine(dir, "replacement.wav");
    File.WriteAllBytes(replacementWav, WavUtil.BuildPcm16Wav(replacementTone, 1, 22050));

    var plan = new InjectPlan(project);
    plan.Add(Replacement.FromWav(1, replacementWav));
    Check(plan.Pending().Count == 1, "replacement queued");
    Check(plan.Pending()[0].NewSampleRate == 22050, "queued WAV metadata read");

    var result = plan.Apply();
    Check(result.ReplacementsApplied == 1, "apply reports 1 replacement");

    // Verify the rebuilt pair.
    string outAcb = Path.Combine(dir, "out.acb");
    string outAwb = Path.Combine(dir, "out.awb");
    File.WriteAllBytes(outAcb, result.ModifiedAcbBytes);
    File.WriteAllBytes(outAwb, result.ModifiedAwbBytes);

    var modified = AcbProject.Open(outAcb);
    var newWf = modified.Waveforms()[1];
    Check(newWf.SampleRate == rate, $"replacement auto-resampled to bank rate (got {newWf.SampleRate})");
    Check(Math.Abs(newWf.DurationSeconds - 2.0) < 0.1, $"ACB NumSamples patched (duration {newWf.DurationSeconds:F2}s)");
    Check(modified.Cues()[1].LengthMs is > 1800 and < 2200, $"cue length patched (got {modified.Cues()[1].LengthMs} ms)");
    Check(modified.Waveforms()[0].DurationSeconds < 1.0, "untouched waveform 0 metadata intact");

    var newAwb = Afs2Archive.Open(outAwb);
    var newBlob = newAwb.GetFileAt(1);
    Check(HcaMeta.LooksLikeHca(newBlob), "replaced AWB slot holds an HCA");
    Check(HcaMeta.Parse(newBlob).HasLoop, "loop preserved through inject");
    var blob0 = newAwb.GetFileAt(0);
    Check(HcaMeta.LooksLikeHca(blob0) && !HcaMeta.Parse(blob0).HasLoop, "untouched slot 0 intact");

    // Decode the replaced slot and PSNR it against the (resampled) source.
    var roundTripped = HcaCodec.DecodeToWav(newBlob);
    var resampledSource = WavUtil.Resample(File.ReadAllBytes(replacementWav), rate);
    var srcFmt = WavUtil.ReadFormat(resampledSource);
    var srcSamples = new short[srcFmt.SampleFrames];
    Buffer.BlockCopy(resampledSource, resampledSource.Length - srcFmt.SampleFrames * 2, srcSamples, 0, srcFmt.SampleFrames * 2);
    double injectPsnr = Psnr(srcSamples, roundTripped);
    Check(injectPsnr >= 30, $"injected audio survives the pipeline (PSNR {injectPsnr:F1} dB)");

    Console.WriteLine();
    Console.WriteLine(failures == 0 ? "ALL TESTS PASSED" : $"{failures} TEST(S) FAILED");
}
finally
{
    try { Directory.Delete(dir, recursive: true); } catch { }
}

return failures == 0 ? 0 : 1;
