using System.Buffers.Binary;
using System.IO;

namespace AcbStudio.Core;

/// <summary>
/// Lightweight HCA header metadata reader (channels, rate, frame count, loop).
/// Decode/encode are handled by VGAudio; this exists so listing a 300-track
/// bank doesn't decode any audio.
/// </summary>
public sealed record HcaMeta(int Channels, int SampleRate, int FrameCount, bool HasLoop)
{
    /// <summary>HCA frames decode to 1024 samples each (parity with the original tool).</summary>
    public int SampleCount => FrameCount * 1024;

    public static bool LooksLikeHca(ReadOnlySpan<byte> data)
        => data.Length >= 4
           && (data[0] & 0x7F) == 'H' && (data[1] & 0x7F) == 'C'
           && (data[2] & 0x7F) == 'A' && (data[3] & 0x7F) == 0;

    public static HcaMeta Parse(ReadOnlySpan<byte> data)
    {
        if (!LooksLikeHca(data))
            throw new InvalidDataException("Not an HCA stream");

        int headerSize = BinaryPrimitives.ReadUInt16BigEndian(data.Slice(6, 2));
        headerSize = Math.Min(headerSize, data.Length);

        int channels = 0, sampleRate = 0, frameCount = 0;
        bool hasLoop = false;

        int pos = 8;
        while (pos + 4 <= headerSize)
        {
            // Chunk magics may have their high bits set on encrypted files; RE4
            // is unencrypted but masking costs nothing.
            uint magic = (uint)(((data[pos] & 0x7F) << 24) | ((data[pos + 1] & 0x7F) << 16)
                              | ((data[pos + 2] & 0x7F) << 8) | (data[pos + 3] & 0x7F));
            switch (magic)
            {
                case 0x666D7400: // "fmt\0"
                    channels = data[pos + 4];
                    sampleRate = (data[pos + 5] << 16) | (data[pos + 6] << 8) | data[pos + 7];
                    frameCount = (int)BinaryPrimitives.ReadUInt32BigEndian(data.Slice(pos + 8, 4));
                    pos += 16;
                    break;
                case 0x636F6D70: // "comp"
                    pos += 16;
                    break;
                case 0x64656300: // "dec\0"
                    pos += 12;
                    break;
                case 0x6C6F6F70: // "loop"
                    hasLoop = true;
                    pos += 16;
                    break;
                case 0x76627200: // "vbr\0"
                    pos += 8;
                    break;
                case 0x61746800: // "ath\0"
                    pos += 6;
                    break;
                case 0x63697068: // "ciph"
                    pos += 6;
                    break;
                case 0x72766100: // "rva\0"
                    pos += 8;
                    break;
                case 0x636F6D6D: // "comm"
                    pos += 5 + data[pos + 4];
                    break;
                case 0x70616400: // "pad\0"
                default:
                    pos = headerSize; // padding or unknown — header is done
                    break;
            }
        }

        if (channels == 0 || sampleRate == 0)
            throw new InvalidDataException("HCA header is missing its fmt chunk");

        return new HcaMeta(channels, sampleRate, frameCount, hasLoop);
    }
}
