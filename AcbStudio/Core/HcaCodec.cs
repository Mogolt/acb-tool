using System.IO;
using VGAudio.Codecs.CriHca;
using VGAudio.Containers.Hca;
using VGAudio.Containers.Wave;
using VGAudio.Formats;

namespace AcbStudio.Core;

public enum HcaQuality
{
    Highest,
    High,
    Middle,
    Low,
    Lowest,
}

/// <summary>
/// HCA decode/encode via VGAudio (the C# HCA reference implementation).
///
/// The Python original had to ship two workarounds here: a smpl-chunk
/// injection hack (its encoder only honored loops via WAV smpl chunks, and
/// its smpl parser crashed) and a hard-coded force_not_looping bypass. With
/// VGAudio we set the loop on the audio object directly, so both
/// workarounds disappear.
/// </summary>
public static class HcaCodec
{
    /// <summary>Default quality: HIGHEST — the only level that cleared the
    /// original tool's 40 dB PSNR validation gate across the RE4 corpus.</summary>
    public const HcaQuality DefaultQuality = HcaQuality.Highest;

    private static CriHcaQuality ToVgAudio(HcaQuality q) => q switch
    {
        HcaQuality.Highest => CriHcaQuality.Highest,
        HcaQuality.High => CriHcaQuality.High,
        HcaQuality.Middle => CriHcaQuality.Middle,
        HcaQuality.Low => CriHcaQuality.Low,
        _ => CriHcaQuality.Lowest,
    };

    /// <summary>Decodes an HCA blob to 16-bit PCM WAV bytes.</summary>
    public static byte[] DecodeToWav(byte[] hcaBytes)
    {
        AudioData audio = new HcaReader().Read(hcaBytes);
        return new WaveWriter().GetFile(audio);
    }

    public static void DecodeToWavFile(byte[] hcaBytes, string wavPath)
        => File.WriteAllBytes(wavPath, DecodeToWav(hcaBytes));

    /// <summary>
    /// Encodes WAV bytes to HCA. When <paramref name="loopWholeFile"/> is set,
    /// the HCA gets a loop chunk spanning the entire waveform — required when
    /// replacing looping cues (BGM, long ambience) so playback doesn't go
    /// silent after one pass.
    /// </summary>
    public static byte[] EncodeWavToHca(byte[] wavBytes, HcaQuality quality = DefaultQuality, bool loopWholeFile = false)
    {
        AudioData audio = new WaveReader().Read(wavBytes);
        if (loopWholeFile)
            audio.SetLoop(true);

        var config = new HcaConfiguration { Quality = ToVgAudio(quality) };
        return new HcaWriter().GetFile(audio, config);
    }

    public static void EncodeWavFileToHcaFile(string wavPath, string hcaPath, HcaQuality quality = DefaultQuality)
        => File.WriteAllBytes(hcaPath, EncodeWavToHca(File.ReadAllBytes(wavPath), quality));
}
