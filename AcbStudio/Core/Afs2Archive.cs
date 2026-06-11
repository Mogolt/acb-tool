using System.Buffers.Binary;
using System.IO;

namespace AcbStudio.Core;

/// <summary>
/// AWB (AFS2) archive: reader + builder.
///
/// The builder carries the KI-001 fix from the original tool: upstream
/// PyCriCodecsEx added a full alignment block to the header even when the
/// header size was already aligned, shifting every waveform offset. This
/// implementation computes offsets by simulating the write sequence, so the
/// offset table can never desynchronize from the payload layout.
/// </summary>
public sealed class Afs2Archive
{
    public byte Version { get; private init; } = 2;
    public byte OffsetIntSize { get; private init; } = 4;
    public ushort IdIntSize { get; private init; } = 2;
    public ushort Alignment { get; private init; } = 0x20;
    public ushort Subkey { get; private init; }
    public int FileCount => _offsets.Count - 1;

    private readonly byte[] _data;
    private readonly List<long> _offsets = [];
    public IReadOnlyList<int> Ids { get; private init; } = [];

    private Afs2Archive(byte[] data) => _data = data;

    public static Afs2Archive Open(string path) => Parse(File.ReadAllBytes(path));

    public static Afs2Archive Parse(byte[] data)
    {
        if (data.Length < 16 || !data.AsSpan(0, 4).SequenceEqual("AFS2"u8))
            throw new InvalidDataException("Invalid AWB header");

        byte version = data[4];
        byte offsetIntSize = data[5];
        ushort idIntSize = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(6, 2));
        uint numFiles = BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(8, 4));
        ushort align = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(12, 2));
        ushort subkey = BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(14, 2));

        var ids = new List<int>((int)numFiles);
        int pos = 16;
        for (int i = 0; i < numFiles; i++)
        {
            ids.Add(idIntSize switch
            {
                1 => data[pos],
                2 => BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(pos, 2)),
                4 => (int)BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(pos, 4)),
                _ => throw new InvalidDataException($"unsupported AWB id int size {idIntSize}"),
            });
            pos += idIntSize;
        }

        var archive = new Afs2Archive(data)
        {
            Version = version,
            OffsetIntSize = offsetIntSize,
            IdIntSize = idIntSize,
            Alignment = align,
            Subkey = subkey,
            Ids = ids,
        };

        // Offset table has numFiles + 1 entries; align each up (reader-side
        // defensive alignment, same as upstream).
        for (int i = 0; i <= numFiles; i++)
        {
            long off = offsetIntSize switch
            {
                2 => BinaryPrimitives.ReadUInt16LittleEndian(data.AsSpan(pos, 2)),
                4 => BinaryPrimitives.ReadUInt32LittleEndian(data.AsSpan(pos, 4)),
                8 => (long)BinaryPrimitives.ReadUInt64LittleEndian(data.AsSpan(pos, 8)),
                _ => throw new InvalidDataException($"unsupported AWB offset int size {offsetIntSize}"),
            };
            pos += offsetIntSize;
            if (off % align != 0)
                off += align - off % align;
            archive._offsets.Add(off);
        }

        return archive;
    }

    public byte[] GetFileAt(int index)
    {
        if (index < 0 || index >= FileCount)
            throw new ArgumentOutOfRangeException(nameof(index));
        long start = _offsets[index];
        long end = Math.Min(_offsets[index + 1], _data.Length);
        return _data.AsSpan((int)start, (int)(end - start)).ToArray();
    }

    /// <summary>Builds a new AWB. Format params default to this archive's values.</summary>
    public static byte[] Build(
        IReadOnlyList<byte[]> blobs,
        ushort subkey = 0,
        byte version = 2,
        ushort idIntSize = 2,
        ushort align = 0x20)
    {
        int numFiles = blobs.Count;
        long totalRaw = blobs.Sum(b => (long)b.Length);

        byte offsetIntSize = totalRaw > 0xFFFFFFFFL ? (byte)8 : (byte)4;

        int headerRawSize = 16 + idIntSize * numFiles + offsetIntSize * (numFiles + 1);

        // KI-001 FIX: pad the header only when it isn't already aligned.
        int headerPaddedSize = headerRawSize % align == 0
            ? headerRawSize
            : headerRawSize + (align - headerRawSize % align);

        // Simulate the payload write sequence to derive the offset table.
        var offsets = new List<long>(numFiles + 1) { headerPaddedSize };
        long cursor = headerPaddedSize;
        for (int i = 0; i < numFiles; i++)
        {
            cursor += blobs[i].Length;
            if (i < numFiles - 1)
            {
                long rem = cursor % align;
                if (rem != 0)
                    cursor += align - rem;
            }
            offsets.Add(cursor);
        }

        using var ms = new MemoryStream();
        using var w = new BinaryWriter(ms);
        w.Write("AFS2"u8);
        w.Write(version);
        w.Write(offsetIntSize);
        w.Write(idIntSize);
        w.Write((uint)numFiles);
        w.Write(align);
        w.Write(subkey);

        for (int i = 0; i < numFiles; i++)
        {
            switch (idIntSize)
            {
                case 2: w.Write((ushort)i); break;
                case 4: w.Write((uint)i); break;
                case 8: w.Write((ulong)i); break;
                default: throw new InvalidDataException($"unsupported AWB id int size {idIntSize}");
            }
        }

        foreach (long off in offsets)
        {
            if (offsetIntSize == 4)
                w.Write((uint)off);
            else
                w.Write((ulong)off);
        }

        while (ms.Length < headerPaddedSize)
            w.Write((byte)0);

        for (int i = 0; i < numFiles; i++)
        {
            w.Write(blobs[i]);
            if (i < numFiles - 1)
            {
                long rem = ms.Length % align;
                if (rem != 0)
                    w.Write(new byte[align - rem]);
            }
        }

        return ms.ToArray();
    }

    public byte[] Rebuild(IReadOnlyList<byte[]> blobs)
        => Build(blobs, Subkey, Version, IdIntSize, Alignment);
}
