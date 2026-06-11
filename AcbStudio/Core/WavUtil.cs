using System.Buffers.Binary;
using System.IO;

namespace AcbStudio.Core;

public sealed record WavFormat(int Channels, int SampleRate, int BitsPerSample, int SampleFrames);

/// <summary>RIFF/WAVE parsing + linear resampling for the inject pipeline.</summary>
public static class WavUtil
{
    /// <summary>Reads format info without loading sample data.</summary>
    public static WavFormat ReadFormat(byte[] wavBytes)
    {
        var (fmt, _, _) = ParseChunks(wavBytes);
        return fmt;
    }

    private static (WavFormat Format, int DataOffset, int DataLength) ParseChunks(byte[] wav)
    {
        if (wav.Length < 12 || !wav.AsSpan(0, 4).SequenceEqual("RIFF"u8) || !wav.AsSpan(8, 4).SequenceEqual("WAVE"u8))
            throw new InvalidDataException("Not a RIFF WAVE file");

        int channels = 0, rate = 0, bits = 0, blockAlign = 0;
        int dataOff = -1, dataLen = 0;

        int pos = 12;
        while (pos + 8 <= wav.Length)
        {
            var id = wav.AsSpan(pos, 4);
            int size = (int)BinaryPrimitives.ReadUInt32LittleEndian(wav.AsSpan(pos + 4, 4));
            int body = pos + 8;

            if (id.SequenceEqual("fmt "u8))
            {
                channels = BinaryPrimitives.ReadUInt16LittleEndian(wav.AsSpan(body + 2, 2));
                rate = (int)BinaryPrimitives.ReadUInt32LittleEndian(wav.AsSpan(body + 4, 4));
                blockAlign = BinaryPrimitives.ReadUInt16LittleEndian(wav.AsSpan(body + 12, 2));
                bits = BinaryPrimitives.ReadUInt16LittleEndian(wav.AsSpan(body + 14, 2));
            }
            else if (id.SequenceEqual("data"u8))
            {
                dataOff = body;
                dataLen = Math.Min(size, wav.Length - body);
            }

            pos = body + size + (size & 1); // chunks are word-aligned
        }

        if (channels == 0 || rate == 0)
            throw new InvalidDataException("WAV file is missing its fmt chunk");
        if (dataOff < 0)
            throw new InvalidDataException("WAV file has no data chunk");

        int frames = blockAlign > 0 ? dataLen / blockAlign : 0;
        return (new WavFormat(channels, rate, bits, frames), dataOff, dataLen);
    }

    /// <summary>
    /// Returns the WAV resampled to <paramref name="targetRate"/> (no-op when
    /// already there). Linear interpolation on 16-bit PCM — same fidelity
    /// class as the original tool's audioop.ratecv path, which game modding
    /// tolerates fine; matching the bank's rate is what actually matters
    /// (Switch RE4 silently drops audio at the wrong rate).
    /// </summary>
    public static byte[] Resample(byte[] wavBytes, int targetRate)
    {
        var (fmt, dataOff, dataLen) = ParseChunks(wavBytes);
        if (fmt.SampleRate == targetRate)
            return wavBytes;
        if (fmt.BitsPerSample != 16)
            throw new InvalidDataException(
                $"Resample requires 16-bit PCM WAV (got {fmt.BitsPerSample}-bit). " +
                "Re-export your WAV as 16-bit and try again.");

        int channels = fmt.Channels;
        int srcFrames = dataLen / (2 * channels);
        long dstFrames = (long)srcFrames * targetRate / fmt.SampleRate;

        var src = new short[srcFrames * channels];
        Buffer.BlockCopy(wavBytes, dataOff, src, 0, srcFrames * channels * 2);

        var dst = new short[dstFrames * channels];
        double step = (double)fmt.SampleRate / targetRate;
        for (long i = 0; i < dstFrames; i++)
        {
            double srcPos = i * step;
            int i0 = (int)srcPos;
            int i1 = Math.Min(i0 + 1, srcFrames - 1);
            double frac = srcPos - i0;
            for (int c = 0; c < channels; c++)
            {
                double a = src[i0 * channels + c];
                double b = src[i1 * channels + c];
                dst[i * channels + c] = (short)Math.Clamp(a + (b - a) * frac, short.MinValue, short.MaxValue);
            }
        }

        return BuildPcm16Wav(dst, channels, targetRate);
    }

    public static byte[] BuildPcm16Wav(short[] interleaved, int channels, int rate)
    {
        int blockAlign = channels * 2;
        int dataSize = interleaved.Length * 2;

        using var ms = new MemoryStream();
        using var w = new BinaryWriter(ms);
        w.Write("RIFF"u8);
        w.Write((uint)(36 + dataSize));
        w.Write("WAVE"u8);
        w.Write("fmt "u8);
        w.Write(16u);
        w.Write((ushort)1);
        w.Write((ushort)channels);
        w.Write((uint)rate);
        w.Write((uint)(rate * blockAlign));
        w.Write((ushort)blockAlign);
        w.Write((ushort)16);
        w.Write("data"u8);
        w.Write((uint)dataSize);
        var bytes = new byte[dataSize];
        Buffer.BlockCopy(interleaved, 0, bytes, 0, dataSize);
        w.Write(bytes);
        return ms.ToArray();
    }
}
