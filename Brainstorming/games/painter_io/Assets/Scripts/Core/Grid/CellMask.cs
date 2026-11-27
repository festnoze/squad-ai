using System;
using System.Collections.Generic;

namespace PainterIO.Core
{
    /// <summary>
    /// Bitset over the Size x Size cells of a grid (contract 5.3), indexed like OwnerGrid.Cells (index = j * Size + i).
    /// Count is maintained incrementally. Version increments on every mutation that changes the content (a Set of a set
    /// cell, an Unset of a clear cell, a Clear of an empty mask and a union that adds nothing leave it unchanged), so it
    /// can key caches such as the pocket hatching texture.
    /// </summary>
    public sealed class CellMask
    {
        private readonly ulong[] words;
        private readonly int cellCount;

        public CellMask(int size)
        {
            if (size <= 0) throw new ArgumentOutOfRangeException(nameof(size), "must be > 0");
            Size = size;
            cellCount = checked(size * size);
            words = new ulong[(cellCount + 63) >> 6];
        }

        /// <summary>Grid side in cells; the mask holds Size * Size cells.</summary>
        public int Size { get; }

        /// <summary>Number of set cells.</summary>
        public int Count { get; private set; }

        /// <summary>Increments on every content change.</summary>
        public int Version { get; private set; }

        public bool Get(int index)
        {
            CheckIndex(index);
            return (words[index >> 6] & (1UL << (index & 63))) != 0UL;
        }

        public void Set(int index)
        {
            CheckIndex(index);
            ulong bit = 1UL << (index & 63);
            ref ulong w = ref words[index >> 6];
            if ((w & bit) != 0UL) return;
            w |= bit;
            Count++;
            Version++;
        }

        public void Unset(int index)
        {
            CheckIndex(index);
            ulong bit = 1UL << (index & 63);
            ref ulong w = ref words[index >> 6];
            if ((w & bit) == 0UL) return;
            w &= ~bit;
            Count--;
            Version++;
        }

        public void Clear()
        {
            if (Count == 0) return;
            Array.Clear(words, 0, words.Length);
            Count = 0;
            Version++;
        }

        /// <summary>Adds every cell of other (same Size required, ArgumentException otherwise).</summary>
        public void UnionWith(CellMask other)
        {
            if (other == null) throw new ArgumentNullException(nameof(other));
            if (other.Size != Size) throw new ArgumentException("CellMask sizes differ: " + other.Size + " vs " + Size, nameof(other));
            if (ReferenceEquals(other, this) || other.Count == 0) return;
            ulong[] src = other.words;
            int count = 0;
            for (int k = 0; k < words.Length; k++)
            {
                ulong w = words[k] | src[k];
                words[k] = w;
                count += PopCount(w);
            }
            if (count != Count)
            {
                Count = count;
                Version++;
            }
        }

        /// <summary>Clears output, then appends the index of every set cell in ascending order.</summary>
        public void CopyIndices(List<int> output)
        {
            if (output == null) throw new ArgumentNullException(nameof(output));
            output.Clear();
            if (Count == 0) return;
            if (output.Capacity < Count) output.Capacity = Count;
            for (int k = 0; k < words.Length; k++)
            {
                ulong w = words[k];
                int baseIndex = k << 6;
                while (w != 0UL)
                {
                    output.Add(baseIndex + TrailingZeroCount(w));
                    w &= w - 1UL; // drop the lowest set bit
                }
            }
        }

        private void CheckIndex(int index)
        {
            if ((uint)index >= (uint)cellCount)
                throw new ArgumentOutOfRangeException(nameof(index), index, "cell index outside [0, Size * Size)");
        }

        // netstandard2.1 has no System.Numerics.BitOperations: portable SWAR versions.
        private static int PopCount(ulong x)
        {
            x -= (x >> 1) & 0x5555555555555555UL;
            x = (x & 0x3333333333333333UL) + ((x >> 2) & 0x3333333333333333UL);
            x = (x + (x >> 4)) & 0x0F0F0F0F0F0F0F0FUL;
            unchecked
            {
                return (int)((x * 0x0101010101010101UL) >> 56);
            }
        }

        private static int TrailingZeroCount(ulong x)
        {
            // x != 0: isolate the lowest set bit, then count the bits below it.
            unchecked
            {
                return PopCount((x & (0UL - x)) - 1UL);
            }
        }
    }
}
