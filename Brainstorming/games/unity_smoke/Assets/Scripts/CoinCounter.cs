namespace Smoke
{
    /// <summary>Pure score logic, kept free of MonoBehaviour so EditMode tests can drive it.</summary>
    public sealed class CoinCounter
    {
        public int Total { get; }
        public int Collected { get; private set; }
        public bool IsComplete => Total > 0 && Collected >= Total;

        public CoinCounter(int total)
        {
            Total = total < 0 ? 0 : total;
        }

        /// <summary>Counts one coin. Returns false once every coin is already counted.</summary>
        public bool Collect()
        {
            if (Collected >= Total)
            {
                return false;
            }
            Collected++;
            return true;
        }

        public string Label => $"Pieces : {Collected}/{Total}";
    }
}
