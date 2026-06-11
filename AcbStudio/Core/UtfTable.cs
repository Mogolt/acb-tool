using System.Buffers.Binary;
using System.IO;
using System.Text;

namespace AcbStudio.Core;

/// <summary>@UTF cell data types (low nibble of the column flag byte).</summary>
public enum UtfType : byte
{
    U8 = 0, S8 = 1, U16 = 2, S16 = 3, U32 = 4, S32 = 5, U64 = 6, S64 = 7,
    F32 = 8, F64 = 9, Str = 0xA, Bytes = 0xB,
}

/// <summary>
/// One cell value. <see cref="Value"/> holds a boxed numeric, a string,
/// a byte[], a nested <see cref="UtfTable"/>, or null (zero-storage column).
/// </summary>
public sealed class UtfValue(UtfType type, object? value)
{
    public UtfType Type { get; } = type;
    public object? Value { get; set; } = value;

    public long AsInt() => Value switch
    {
        byte b => b, sbyte sb => sb, ushort us => us, short s => s,
        uint ui => ui, int i => i, ulong ul => (long)ul, long l => l,
        null => 0,
        _ => throw new InvalidDataException($"not an integer cell ({Type})"),
    };

    public override string ToString() => $"{Type}:{Value}";
}

/// <summary>
/// CRI @UTF table: big-endian schema'd rows used by ACB files.
///
/// The serializer mirrors PyCriCodecsEx's UTFBuilder semantics exactly
/// (storage-class re-inference, string-table layout, substring-deduped data
/// area) because that output is what's been verified working on RE4 hardware.
/// </summary>
public sealed class UtfTable
{
    public string Name = "";
    public Encoding StringEncoding = Encoding.UTF8;
    public List<string> Columns = [];
    public List<Dictionary<string, UtfValue>> Rows = [];

    static UtfTable()
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
    }

    public static bool LooksLikeUtf(ReadOnlySpan<byte> data)
        => data.Length >= 4 && data[..4].SequenceEqual("@UTF"u8);

    // ── Parsing ──────────────────────────────────────────────────────────────

    public static UtfTable Parse(byte[] data)
    {
        if (!LooksLikeUtf(data))
            throw new InvalidDataException("@UTF chunk is not present");

        uint ReadU32(int off) => BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(off, 4));
        ushort ReadU16(int off) => BinaryPrimitives.ReadUInt16BigEndian(data.AsSpan(off, 2));

        // Offsets in the header are relative to file offset 8.
        uint rowsOffset = ReadU32(8);
        uint stringOffset = ReadU32(12);
        uint dataOffset = ReadU32(16);
        uint tableNamePtr = ReadU32(20);
        int numColumns = ReadU16(24);
        int numRows = (int)ReadU32(28);

        var table = new UtfTable();

        // String region [stringOffset+8, dataOffset+8) — split on NUL.
        int strBase = (int)stringOffset + 8;
        int strEnd = Math.Min((int)dataOffset + 8, data.Length);
        var stringRegion = data.AsSpan(strBase, Math.Max(0, strEnd - strBase)).ToArray();

        Encoding encoding = Encoding.UTF8;
        string DecodeString(int regionOffset)
        {
            if (regionOffset < 0 || regionOffset >= stringRegion.Length)
                return "";
            int end = Array.IndexOf(stringRegion, (byte)0, regionOffset);
            if (end < 0)
                end = stringRegion.Length;
            var raw = stringRegion.AsSpan(regionOffset, end - regionOffset);
            try
            {
                return Encoding.GetEncoding("utf-8", EncoderFallback.ExceptionFallback, DecoderFallback.ExceptionFallback)
                    .GetString(raw);
            }
            catch (DecoderFallbackException)
            {
                encoding = Encoding.GetEncoding(932); // shift-jis
                return encoding.GetString(raw);
            }
        }

        table.Name = DecodeString((int)tableNamePtr);

        // Column records start right after the 32-byte header.
        int pos = 0x20;
        var columns = new List<(string Name, byte StorageFlag, UtfType Type, UtfValue? Constant)>(numColumns);

        UtfValue ReadTyped(UtfType t, ref int p)
        {
            switch (t)
            {
                case UtfType.U8: { var v = data[p]; p += 1; return new UtfValue(t, v); }
                case UtfType.S8: { var v = (sbyte)data[p]; p += 1; return new UtfValue(t, v); }
                case UtfType.U16: { var v = BinaryPrimitives.ReadUInt16BigEndian(data.AsSpan(p, 2)); p += 2; return new UtfValue(t, v); }
                case UtfType.S16: { var v = BinaryPrimitives.ReadInt16BigEndian(data.AsSpan(p, 2)); p += 2; return new UtfValue(t, v); }
                case UtfType.U32: { var v = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(p, 4)); p += 4; return new UtfValue(t, v); }
                case UtfType.S32: { var v = BinaryPrimitives.ReadInt32BigEndian(data.AsSpan(p, 4)); p += 4; return new UtfValue(t, v); }
                case UtfType.U64: { var v = BinaryPrimitives.ReadUInt64BigEndian(data.AsSpan(p, 8)); p += 8; return new UtfValue(t, v); }
                case UtfType.S64: { var v = BinaryPrimitives.ReadInt64BigEndian(data.AsSpan(p, 8)); p += 8; return new UtfValue(t, v); }
                case UtfType.F32: { var v = BinaryPrimitives.ReadSingleBigEndian(data.AsSpan(p, 4)); p += 4; return new UtfValue(t, v); }
                case UtfType.F64: { var v = BinaryPrimitives.ReadDoubleBigEndian(data.AsSpan(p, 8)); p += 8; return new UtfValue(t, v); }
                case UtfType.Str:
                {
                    var off = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(p, 4)); p += 4;
                    return new UtfValue(t, DecodeString((int)off));
                }
                case UtfType.Bytes:
                {
                    var off = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(p, 4)); p += 4;
                    var len = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(p, 4)); p += 4;
                    var blob = data.AsSpan((int)(dataOffset + 8 + off), (int)len).ToArray();
                    return new UtfValue(t, blob);
                }
                default:
                    throw new InvalidDataException($"unknown @UTF data type {t}");
            }
        }

        for (int c = 0; c < numColumns; c++)
        {
            byte flag = data[pos++];
            byte storage = (byte)(flag >> 4);
            var type = (UtfType)(flag & 0xF);

            uint nameOff = BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(pos, 4));
            pos += 4;
            string name = DecodeString((int)nameOff);

            switch (storage)
            {
                case 0x1: // zero storage — value is "nothing"
                    columns.Add((name, storage, type, new UtfValue(type,
                        type == UtfType.Str ? "<NULL>" : type == UtfType.Bytes ? Array.Empty<byte>() : null)));
                    break;
                case 0x3: // constant — inline value
                {
                    var v = ReadTyped(type, ref pos);
                    columns.Add((name, storage, type, v));
                    break;
                }
                case 0x5: // per-row
                    columns.Add((name, storage, type, null));
                    break;
                default:
                    throw new InvalidDataException($"unsupported @UTF storage flag 0x{storage:X}0");
            }
        }

        table.Columns = columns.Select(c => c.Name).ToList();

        // Rows.
        int rowPos = (int)rowsOffset + 8;
        for (int r = 0; r < numRows; r++)
        {
            var row = new Dictionary<string, UtfValue>();
            foreach (var col in columns)
            {
                if (col.StorageFlag == 0x5)
                {
                    row[col.Name] = ReadTyped(col.Type, ref rowPos);
                }
                else
                {
                    var constant = col.Constant!;
                    row[col.Name] = new UtfValue(constant.Type, constant.Value);
                }
            }
            table.Rows.Add(row);
        }

        // Zero-row tables still describe one "row" of constants (python parity).
        if (numRows == 0)
        {
            var row = new Dictionary<string, UtfValue>();
            foreach (var col in columns)
            {
                var constant = col.Constant ?? new UtfValue(col.Type, null);
                row[col.Name] = new UtfValue(constant.Type, constant.Value);
            }
            table.Rows.Add(row);
        }

        table.StringEncoding = encoding;

        // Recursively expand nested @UTF blobs.
        foreach (var row in table.Rows)
        {
            foreach (var key in table.Columns)
            {
                if (row[key].Value is byte[] blob && LooksLikeUtf(blob))
                    row[key].Value = Parse(blob);
            }
        }

        return table;
    }

    /// <summary>Returns the nested table stored in a column of the (single-row) root, or null.</summary>
    public UtfTable? NestedTable(string column)
        => Rows.Count > 0 && Rows[0].TryGetValue(column, out var v) ? v.Value as UtfTable : null;

    public UtfValue Cell(int row, string column) => Rows[row][column];

    // ── Serialization (mirrors PyCriCodecsEx UTFBuilder) ─────────────────────

    public byte[] Serialize()
    {
        // 1. Recursively serialize nested tables to raw bytes (work on a copy).
        var rows = Rows.Select(r =>
        {
            var copy = new Dictionary<string, UtfValue>();
            foreach (var key in Columns)
            {
                var v = r[key];
                copy[key] = v.Value is UtfTable nested
                    ? new UtfValue(UtfType.Bytes, nested.Serialize())
                    : new UtfValue(v.Type, v.Value);
            }
            return copy;
        }).ToList();

        // 2. Build the string list: column names (in order), then string values
        //    (row-major first-occurrence), deduped against everything before.
        var strings = new List<string>();
        foreach (var key in Columns)
            if (!strings.Contains(key))
                strings.Add(key);
        foreach (var row in rows)
            foreach (var key in Columns)
                if (row[key].Value is string s && !strings.Contains(s))
                    strings.Add(s);

        // Data area: concatenated byte blobs, deduped by substring containment.
        var binary = new List<byte>();
        bool ContainsBlob(byte[] blob)
            => blob.Length == 0 || IndexOfBlob(binary, blob) >= 0;
        foreach (var row in rows)
            foreach (var key in Columns)
                if (row[key].Value is byte[] blob && !ContainsBlob(blob))
                    binary.AddRange(blob);
        var binaryArr = binary.ToArray();

        strings.Insert(0, Name);
        int nullIdx = strings.IndexOf("<NULL>");
        if (nullIdx >= 0)
        {
            strings.RemoveAt(nullIdx);
            strings.Insert(0, "<NULL>");
        }

        // Encode strings and compute first-occurrence offsets.
        var encoded = strings.Select(s => StringEncoding.GetBytes(s)).ToList();
        var stringOffsets = new Dictionary<string, int>();
        int cursor = 0;
        for (int i = 0; i < strings.Count; i++)
        {
            if (!stringOffsets.ContainsKey(strings[i]))
                stringOffsets[strings[i]] = cursor;
            cursor += encoded[i].Length + 1;
        }
        var stringBlob = new byte[cursor];
        cursor = 0;
        foreach (var e in encoded)
        {
            e.CopyTo(stringBlob, cursor);
            cursor += e.Length + 1; // NUL terminator
        }

        // 3. Storage-class inference per column (python parity).
        // entries: (storageFlag, type, name, constantValue?)
        var schema = new List<(byte Storage, UtfType Type, string Name, object? Constant)>();
        foreach (var key in Columns)
        {
            var first = rows[0][key];
            if (rows.Count != 1)
            {
                bool allEqual = rows.All(r => CellEquals(r[key].Value, first.Value));
                if (!allEqual)
                    schema.Add((0x50, first.Type, key, null));
                else if (first.Value is null)
                    schema.Add((0x10, first.Type, key, null));
                else
                    schema.Add((0x30, first.Type, key, first.Value));
            }
            else
            {
                if (first.Value is null || (first.Value is string ns && ns == "<NULL>"))
                    schema.Add((0x10, first.Type, key, null));
                else
                    schema.Add((0x50, first.Type, key, null));
            }
        }

        // 4. Column records.
        using var colMs = new MemoryStream();
        foreach (var col in schema)
        {
            colMs.WriteByte((byte)(col.Storage | (byte)col.Type));
            WriteU32Be(colMs, (uint)stringOffsets[col.Name]);
            if (col.Storage == 0x30)
                WriteTyped(colMs, col.Type, col.Constant, stringOffsets, binaryArr);
        }
        var columnData = colMs.ToArray();

        // 5. Row records (per-row columns only).
        using var rowMs = new MemoryStream();
        foreach (var row in rows)
        {
            foreach (var col in schema)
            {
                if (col.Storage != 0x50)
                    continue;
                WriteTyped(rowMs, col.Type, row[col.Name].Value, stringOffsets, binaryArr);
            }
        }
        var rowData = rowMs.ToArray();

        // 6. Header + assembly.
        int dataLen = columnData.Length + rowData.Length + stringBlob.Length + binaryArr.Length + 0x18;
        int chunkSize = dataLen % 8 == 0 ? dataLen : dataLen + (8 - dataLen % 8);
        int binaryOffset = binaryArr.Length == 0 ? chunkSize : dataLen - binaryArr.Length;
        int stringOffset = dataLen - stringBlob.Length - binaryArr.Length;
        int rowLength = schema.Where(c => c.Storage == 0x50).Sum(c => TypeSize(c.Type));

        using var outMs = new MemoryStream();
        outMs.Write("@UTF"u8);
        WriteU32Be(outMs, (uint)chunkSize);
        WriteU32Be(outMs, (uint)(columnData.Length + 0x18));
        WriteU32Be(outMs, (uint)stringOffset);
        WriteU32Be(outMs, (uint)binaryOffset);
        WriteU32Be(outMs, (uint)stringOffsets[Name]);
        WriteU16Be(outMs, (ushort)schema.Count);
        WriteU16Be(outMs, (ushort)rowLength);
        WriteU32Be(outMs, (uint)rows.Count);
        outMs.Write(columnData);
        outMs.Write(rowData);
        outMs.Write(stringBlob);
        outMs.Write(binaryArr);

        // Pad so that (total - 8) == chunkSize.
        while (outMs.Length < chunkSize + 8)
            outMs.WriteByte(0);

        return outMs.ToArray();
    }

    private static bool CellEquals(object? a, object? b)
    {
        if (a is byte[] ba && b is byte[] bb)
            return ba.AsSpan().SequenceEqual(bb);
        return Equals(a, b);
    }

    private static int TypeSize(UtfType t) => t switch
    {
        UtfType.U8 or UtfType.S8 => 1,
        UtfType.U16 or UtfType.S16 => 2,
        UtfType.U32 or UtfType.S32 or UtfType.F32 or UtfType.Str => 4,
        UtfType.U64 or UtfType.S64 or UtfType.F64 or UtfType.Bytes => 8,
        _ => throw new InvalidDataException($"unknown @UTF type {t}"),
    };

    private void WriteTyped(MemoryStream ms, UtfType type, object? value,
        Dictionary<string, int> stringOffsets, byte[] binaryArr)
    {
        switch (type)
        {
            case UtfType.U8: ms.WriteByte((byte)ToLong(value)); break;
            case UtfType.S8: ms.WriteByte(unchecked((byte)(sbyte)ToLong(value))); break;
            case UtfType.U16: WriteU16Be(ms, (ushort)ToLong(value)); break;
            case UtfType.S16: WriteU16Be(ms, unchecked((ushort)(short)ToLong(value))); break;
            case UtfType.U32: WriteU32Be(ms, (uint)ToLong(value)); break;
            case UtfType.S32: WriteU32Be(ms, unchecked((uint)(int)ToLong(value))); break;
            case UtfType.U64: WriteU64Be(ms, value is ulong ul ? ul : (ulong)ToLong(value)); break;
            case UtfType.S64: WriteU64Be(ms, unchecked((ulong)ToLong(value))); break;
            case UtfType.F32:
            {
                Span<byte> b = stackalloc byte[4];
                BinaryPrimitives.WriteSingleBigEndian(b, Convert.ToSingle(value));
                ms.Write(b);
                break;
            }
            case UtfType.F64:
            {
                Span<byte> b = stackalloc byte[8];
                BinaryPrimitives.WriteDoubleBigEndian(b, Convert.ToDouble(value));
                ms.Write(b);
                break;
            }
            case UtfType.Str:
                WriteU32Be(ms, (uint)stringOffsets[(string)value!]);
                break;
            case UtfType.Bytes:
            {
                var blob = (byte[])value!;
                int off = blob.Length == 0 ? 0 : IndexOfBlob(binaryArr, blob);
                if (off < 0)
                    throw new InvalidDataException("blob missing from data area");
                WriteU32Be(ms, (uint)off);
                WriteU32Be(ms, (uint)blob.Length);
                break;
            }
            default:
                throw new InvalidDataException($"unknown @UTF type {type}");
        }
    }

    private static long ToLong(object? value) => value switch
    {
        byte b => b, sbyte sb => sb, ushort us => us, short s => s,
        uint ui => ui, int i => i, ulong ul => (long)ul, long l => l,
        null => 0,
        _ => Convert.ToInt64(value),
    };

    private static int IndexOfBlob(IReadOnlyList<byte> haystack, byte[] needle)
    {
        if (haystack is List<byte> list)
            return ((ReadOnlySpan<byte>)System.Runtime.InteropServices.CollectionsMarshal.AsSpan(list)).IndexOf(needle);
        return ((ReadOnlySpan<byte>)(byte[])haystack).IndexOf(needle);
    }

    private static void WriteU16Be(MemoryStream ms, ushort v)
    {
        Span<byte> b = stackalloc byte[2];
        BinaryPrimitives.WriteUInt16BigEndian(b, v);
        ms.Write(b);
    }

    private static void WriteU32Be(MemoryStream ms, uint v)
    {
        Span<byte> b = stackalloc byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(b, v);
        ms.Write(b);
    }

    private static void WriteU64Be(MemoryStream ms, ulong v)
    {
        Span<byte> b = stackalloc byte[8];
        BinaryPrimitives.WriteUInt64BigEndian(b, v);
        ms.Write(b);
    }
}
