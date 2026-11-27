// Owned by domain (rule v1.8, contract section 32). Stress invariant: in every round type (classic and the three biome
// sets), on the square arena and on country outlines, with the lasso on and off, bot-only and with a human proxy, every
// living player's territory is exactly ONE 8-connected component after every tick. Every violation is logged with the
// event that caused it; diagonal-only connections (a corner neck that looks broken on screen) are measured.
// Pure NUnit + PainterIO.Core (no UnityEngine), NUnit 3.5 features only.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Text;
using NUnit.Framework;
using PainterIO.Core;

namespace PainterIO.Tests
{
    public class SingleDomainStressTests
    {
        // ------------------------------------------------------------------------------------------------------------
        // Country outlines: the "level" polygons of Assets/Resources/Europe/countries.json (normalized, rounded to 1e-5)
        // and their levelCenter. Copied here because Core tests cannot load Unity resources; the arena is built exactly
        // like Runtime EuropeCatalog.Country.Configure (scale ArenaHalfSize - 1.2, start search, start disc radius).

        internal enum ArenaKind { Square, Croatia, Greece, Italy, Norway }

        private static readonly double[] CroatiaOutline =
        {
            -0.99975,0.28212, -0.98464,0.20344, -0.961,0.19212, -0.96,0.10458, -0.91732,0.10536, -0.95551,0.09551, -0.9509,0.07428,
            -0.8487,-0.06456, -0.84379,-0.06149, -0.85459,-0.03561, -0.81663,-0.04339, -0.82809,-0.00183, -0.79506,0.03952,
            -0.80846,0.06526, -0.79236,0.04096, -0.79654,0.02307, -0.76543,0.04693, -0.72437,0.21612, -0.63132,0.19357,
            -0.53419,0.10783, -0.5068,0.04498, -0.51268,-0.06815, -0.46816,-0.13474, -0.27831,-0.27372, -0.3714,-0.24598,
            -0.35709,-0.28423, -0.41128,-0.27278, -0.40723,-0.31419, -0.28749,-0.4369, -0.21012,-0.4838, -0.22598,-0.48566,
            -0.11789,-0.54152, -0.09699,-0.62299, -0.04748,-0.6306, -0.02724,-0.62377, -0.04756,-0.60875, 0.0615,-0.58749,
            0.04824,-0.6073, 0.22276,-0.64214, 0.4875,-0.83925, 0.51522,-0.82509, 0.49952,-0.78785, 0.36979,-0.67742,
            0.35607,-0.60203, 0.26898,-0.56942, 0.00405,-0.33685, -0.03896,-0.2801, -0.08471,-0.13354, -0.12319,-0.12729,
            -0.11865,-0.08675, -0.16733,-0.04561, -0.19721,-0.05847, -0.21436,-0.0418, -0.23048,-0.01795, -0.21342,0.01146,
            -0.23078,0.04956, -0.21916,0.17646, -0.15085,0.19567, -0.07095,0.11241, -0.0267,0.10388, 0.02851,0.21255,
            0.11719,0.19964, 0.15936,0.25432, 0.25387,0.19793, 0.2797,0.22015, 0.3574,0.19262, 0.42117,0.22208, 0.47687,0.18,
            0.52462,0.2233, 0.58264,0.20733, 0.60806,0.23898, 0.70744,0.20126, 0.71167,0.2184, 0.76419,0.2196, 0.8019,0.18812,
            0.80493,0.14414, 0.84371,0.12342, 0.88619,0.13069, 0.87524,0.15313, 0.92054,0.17711, 0.88201,0.25688,
            0.91183,0.26906, 0.90374,0.29207, 1,0.29633, 0.99479,0.31672, 0.84554,0.36958, 0.84929,0.43151, 0.8809,0.44164,
            0.80974,0.46263, 0.82617,0.51075, 0.77855,0.57295, 0.7894,0.63293, 0.74613,0.60498, 0.71514,0.61406,
            0.63649,0.52439, 0.45431,0.51896, 0.37968,0.54577, 0.35363,0.5868, 0.27095,0.58784, 0.21436,0.6619,
            0.13666,0.69748, 0.08396,0.77496, -0.08563,0.83925, -0.11956,0.81059, -0.10004,0.75595, -0.17361,0.75046,
            -0.1901,0.7078, -0.30602,0.65842, -0.31934,0.6122, -0.28067,0.57803, -0.28417,0.47956, -0.35541,0.46629,
            -0.41548,0.42129, -0.37556,0.38087, -0.40962,0.35994, -0.37452,0.30505, -0.38942,0.28885, -0.44764,0.27495,
            -0.52319,0.31056, -0.56395,0.28404, -0.60927,0.31413, -0.63868,0.37435, -0.70727,0.28128, -0.84324,0.29109,
            -0.86899,0.24633,
        };

        private static readonly double[] GreeceOutline =
        {
            -0.17303,0.68093, -0.17562,0.61928, -0.34543,0.59541, -0.452,0.47927, -0.61113,0.44948, -0.58485,0.34904,
            -0.64056,0.29937, -0.6621,0.17883, -0.74472,0.13261, -0.71572,0.0702, -0.74631,0.06544, -0.74783,0.019,
            -0.81433,0.02067, -0.76324,0.00361, -0.73944,-0.07106, -0.6689,-0.10176, -0.58706,-0.20538, -0.5754,-0.14788,
            -0.47559,-0.17273, -0.48955,-0.221, -0.57817,-0.20105, -0.58223,-0.25542, -0.50946,-0.29032, -0.44544,-0.40857,
            -0.40916,-0.33657, -0.34566,-0.39643, -0.22616,-0.33806, -0.11663,-0.34396, -0.11698,-0.30557, -0.06177,-0.35312,
            -0.04799,-0.31616, 0.00317,-0.36417, 0.11918,-0.3677, 0.02609,-0.42694, 0.06176,-0.44033, 0.03458,-0.45869,
            -0.26004,-0.36743, -0.3176,-0.44203, -0.3826,-0.42805, -0.3866,-0.49762, -0.43978,-0.5551, -0.26293,-0.69537,
            -0.28124,-0.7811, -0.22723,-0.88985, -0.17468,-0.91334, -0.16789,-0.81638, -0.11421,-0.80179, 0.00948,-1,
            -0.00301,-0.92734, 0.04243,-0.84952, 0.20227,-0.95301, 0.01585,-0.60001, 0.13188,-0.61249, 0.14965,-0.6612,
            0.23835,-0.58988, 0.19432,-0.53576, 0.17913,-0.57337, 0.13316,-0.55476, 0.12663,-0.48813, 0.07531,-0.45668,
            0.22166,-0.3888, 0.34144,-0.49536, 0.37264,-0.45201, 0.32716,-0.34291, 0.34932,-0.32366, 0.30752,-0.2879,
            0.22929,-0.27943, 0.18598,-0.23317, 0.12895,-0.24451, 0.10959,-0.1958, -0.10432,-0.16289, 0.03056,-0.08063,
            0.00479,-0.09197, -0.04291,-0.02629, -0.02117,0.02593, 0.06109,-0.01899, 0.02353,-0.05785, 0.06342,-0.0485,
            0.09653,-0.01651, -0.15343,0.24492, -0.17289,0.38577, -0.0961,0.46031, -0.0881,0.37166, 0.02714,0.33921,
            0.05828,0.24907, 0.16137,0.25705, 0.04865,0.3134, 0.06106,0.36054, 0.2237,0.27667, 0.21419,0.33258,
            0.13315,0.36732, 0.13256,0.40137, 0.3171,0.36394, 0.20034,0.44548, 0.16522,0.42646, 0.11567,0.53942,
            0.20964,0.54468, 0.26985,0.6292, 0.38036,0.62179, 0.45695,0.69214, 0.69919,0.6806, 0.7166,0.65025, 0.7722,0.74309,
            0.7432,0.8359, 0.81433,0.89837, 0.78764,0.97493, 0.68131,1, 0.64414,0.97026, 0.6849,0.86242, 0.62777,0.83116,
            0.46807,0.77545, 0.36807,0.81123, 0.34279,0.78775, 0.26237,0.84678,
        };

        private static readonly double[] ItalyOutline =
        {
            0.11972,0.67734, 0.14791,0.68739, 0.0765,0.76736, 0.10196,0.80737, 0.05876,0.82984, 0.10818,0.88335,
            -0.09246,0.91308, -0.1365,0.96049, -0.1294,1, -0.28501,0.96782, -0.30886,0.92572, -0.39226,0.94614,
            -0.39122,0.87693, -0.43218,0.89304, -0.45668,0.8721, -0.44999,0.80241, -0.47732,0.8363, -0.52984,0.8188,
            -0.54837,0.86331, -0.57234,0.8647, -0.61741,0.71454, -0.65343,0.75124, -0.64668,0.77488, -0.70523,0.81198,
            -0.71727,0.85511, -0.79957,0.73929, -0.84425,0.7562, -0.9608,0.7255, -0.90806,0.63078, -0.92707,0.58788,
            -0.99868,0.56608, -0.97795,0.52157, -0.9372,0.50077, -0.93071,0.46997, -0.96698,0.43787, -0.94744,0.3737,
            -0.88947,0.34351, -0.83848,0.35346, -0.8658,0.26895, -0.77379,0.28946, -0.70771,0.3786, -0.65975,0.40615,
            -0.45603,0.31905, -0.37732,0.14573, -0.37971,0.07322, -0.33843,0.07018, -0.34138,0.04331, -0.27033,-0.0092,
            -0.28041,-0.04517, -0.18648,-0.07086, -0.15716,-0.12463, 0.05227,-0.29696, 0.16626,-0.28634, 0.22505,-0.38458,
            0.26752,-0.37284, 0.29935,-0.39523, 0.27886,-0.43175, 0.35241,-0.40528, 0.39283,-0.46317, 0.38,-0.49864,
            0.44288,-0.54157, 0.50445,-0.52639, 0.62596,-0.77878, 0.62128,-0.81264, 0.56409,-0.83667, 0.57753,-0.87701,
            0.53349,-0.9366, 0.54303,-0.99209, 0.60309,-0.99811, 0.69378,-0.88029, 0.68972,-0.79874, 0.73346,-0.7653,
            0.78006,-0.76528, 0.79543,-0.73483, 0.78003,-0.65249, 0.66963,-0.60582, 0.65798,-0.58139, 0.71827,-0.42696,
            0.78717,-0.40861, 0.7702,-0.4308, 0.88064,-0.44569, 0.92692,-0.52519, 0.97365,-0.54423, 0.99789,-0.46662,
            0.90004,-0.36322, 0.54002,-0.21634, 0.5273,-0.18279, 0.57329,-0.13984, 0.56239,-0.112, 0.39996,-0.12243,
            0.3272,-0.09232, 0.21085,0.01526, 0.1254,0.22486, -0.0734,0.35815, -0.10407,0.47206, -0.0602,0.53098,
            -0.12312,0.60073, -0.10476,0.63945, 0.02117,0.6837, 0.02411,0.71183, 0.07039,0.69331, 0.10489,0.7166,
        };

        private static readonly double[] NorwayOutline =
        {
            -0.23974,-0.85959, -0.14554,-0.51495, -0.21672,-0.23662, -0.0833,-0.10342, -0.07832,0.18001, 0.02798,0.44701,
            0.10443,0.55165, 0.19299,0.53305, 0.23839,0.67549, 0.31216,0.60328, 0.44664,0.60786, 0.52852,0.85247,
            0.64135,0.72847, 0.70388,0.84385, 0.56938,0.87756, 0.66588,0.95097, 0.54773,0.97839, 0.54808,0.85696,
            0.48424,0.99896, 0.40538,0.82383, 0.41494,0.94112, 0.35162,0.94466, 0.32103,0.78677, 0.22211,0.82254,
            0.26534,0.74568, 0.21987,0.78033, 0.16894,0.66052, 0.17787,0.75319, 0.14437,0.67697, 0.12183,0.72861,
            0.14708,0.65245, 0.07271,0.676, 0.00015,0.53107, 0.07764,0.52223, -0.08393,0.42219, -0.02502,0.35427,
            -0.10192,0.33981, -0.0224,0.33571, -0.17398,0.23215, -0.16586,0.18224, -0.10417,0.206, -0.12111,0.18056,
            -0.1888,0.16524, -0.17598,0.04384, -0.37706,-0.16819, -0.34246,-0.20686, -0.26066,-0.11791, -0.28781,-0.2124,
            -0.43459,-0.21852, -0.43431,-0.30517, -0.48855,-0.27662, -0.44537,-0.32883, -0.55323,-0.28595, -0.47193,-0.32317,
            -0.59881,-0.33247, -0.52623,-0.38209, -0.5399,-0.4063, -0.54222,-0.40437, -0.55135,-0.40749, -0.55575,-0.40564,
            -0.57009,-0.35436, -0.5963,-0.40964, -0.68166,-0.38529, -0.68077,-0.42853, -0.66174,-0.42374, -0.62528,-0.42904,
            -0.59063,-0.44414, -0.56669,-0.43788, -0.61145,-0.45158, -0.62524,-0.44145, -0.63114,-0.45453, -0.66422,-0.42746,
            -0.69495,-0.45039, -0.64032,-0.49568, -0.68646,-0.54293, -0.50964,-0.53346, -0.55334,-0.58555, -0.6996,-0.55056,
            -0.65714,-0.70665, -0.55557,-0.63703, -0.70214,-0.76931, -0.68448,-0.80836, -0.60293,-0.77211, -0.67856,-0.9148,
            -0.57949,-1, -0.48605,-0.98488, -0.32469,-0.85077, -0.29733,-0.7271,
        };

        private static void Outline(ArenaKind kind, out double[] outline, out Vec2d center)
        {
            switch (kind)
            {
                case ArenaKind.Croatia: outline = CroatiaOutline; center = new Vec2d(-0.015988, 0.476992); return;
                case ArenaKind.Greece: outline = GreeceOutline; center = new Vec2d(-0.393066, 0.096191); return;
                case ArenaKind.Italy: outline = ItalyOutline; center = new Vec2d(-0.374065, 0.559987); return;
                case ArenaKind.Norway: outline = NorwayOutline; center = new Vec2d(-0.331476, -0.512462); return;
                default: throw new ArgumentException("not a country: " + kind);
            }
        }

        /// <summary>Runtime EuropeCatalog.Country.Configure, replicated: polygon arena, starts and start disc radius.</summary>
        internal static void ConfigureCountry(ArenaKind kind, SimConfig config, SimSetup setup)
        {
            Outline(kind, out double[] outline, out Vec2d levelCenter);
            double scale = config.ArenaHalfSize - 1.2;
            Vec2d center = levelCenter * scale;
            var points = new Vec2d[outline.Length / 2];
            for (int k = 0; k < points.Length; k++) points[k] = new Vec2d(outline[2 * k] * scale, outline[2 * k + 1] * scale);
            var polygon = new ArenaPolygon(points, center);
            config.ArenaBoundary = polygon;

            var candidates = new List<Vec2d>();
            double inset = config.ArenaMargin + 0.3;
            if (polygon.Distance(center, out _) < -inset) candidates.Add(center);
            for (double y = -scale; y <= scale; y += 1.0)
            for (double x = -scale; x <= scale; x += 1.0)
            {
                var p = new Vec2d(x, y);
                if (polygon.Distance(p, out _) < -inset) candidates.Add(p);
            }
            var starts = new Vec2d[setup.PlayerCount];
            var headings = new double[starts.Length];
            double safeRadius = config.StartDiscRadius;
            for (int player = 0; player < starts.Length; player++)
            {
                double best = double.NegativeInfinity;
                foreach (Vec2d candidate in candidates)
                {
                    double clearance = -polygon.Distance(candidate, out _);
                    double separation = double.PositiveInfinity;
                    for (int i = 0; i < player; i++) separation = Math.Min(separation, Vec2d.Distance(starts[i], candidate));
                    double score = Math.Min(separation * 0.5, clearance * 2.5);
                    if (score <= best) continue;
                    best = score;
                    starts[player] = candidate;
                }
                if (!(best > 0)) throw new InvalidOperationException("no start for " + kind);
                headings[player] = (center - starts[player]).Angle();
                double edgeRoom = -polygon.Distance(starts[player], out _) - 0.15;
                safeRadius = Math.Min(safeRadius, Math.Min(edgeRoom, best * 0.8));
            }
            config.StartDiscRadius = safeRadius;
            setup.StartPositions = starts;
            setup.StartHeadings = headings;
        }

        // ------------------------------------------------------------------------------------------------------------
        // Rounds

        internal static readonly string[] SetNames = { "Classic", "Liquide v1.1", "Feu v1.1", "Electricite v1.1" };

        internal static RuleTraits SetOf(int set)
        {
            switch (set)
            {
                case 1: return TraitTestKit.LiquidV11;
                case 2: return TraitTestKit.FireV11;
                case 3: return TraitTestKit.ElectricV11;
                default: return RuleTraits.Classic;
            }
        }

        /// <summary>The section 9 human proxy (BotsReport_HumanProxyFixture): a slower, less aggressive Balanced bot.</summary>
        internal static BotPersonality HumanProxy()
        {
            BotPersonality proxy = BotPersonality.Preset(BotStyle.Balanced);
            proxy.ReactionDelay = 0.45;
            proxy.SenseRadius = 12;
            proxy.AttackChance = 0.3;
            return proxy;
        }

        /// <summary>
        /// One full round: four bots (TraitTestKit.Lineup), or the human proxy as player 0 (HumanIndex 0) against Balanced,
        /// Greedy and Aggressive; the trait set, the lasso switch, the arena and the tick rate as given.
        /// </summary>
        internal static Simulation BuildRound(ulong seed, ArenaKind arena, int set, bool lasso, bool proxy, int rate,
                                              Action<SimConfig> tweak = null)
        {
            var config = new SimConfig { Seed = seed, TickRate = rate, LassoEnabled = lasso, Traits = SetOf(set) };
            tweak?.Invoke(config);
            var setup = new SimSetup { HumanIndex = proxy ? 0 : -1, PlayerCount = 4 };
            if (arena != ArenaKind.Square) ConfigureCountry(arena, config, setup);
            var personalities = proxy
                ? new[] { HumanProxy(), BotPersonality.Preset(BotStyle.Balanced), BotPersonality.Preset(BotStyle.Greedy), BotPersonality.Preset(BotStyle.Aggressive) }
                : new[] { BotPersonality.Preset(TraitTestKit.Lineup[0]), BotPersonality.Preset(TraitTestKit.Lineup[1]),
                          BotPersonality.Preset(TraitTestKit.Lineup[2]), BotPersonality.Preset(TraitTestKit.Lineup[3]) };
            var controllers = new IController[4];
            for (int i = 0; i < 4; i++) controllers[i] = new BotController(personalities[i], BotTests.BotSeed(seed, i));
            return new Simulation(config, controllers, setup);
        }

        // ------------------------------------------------------------------------------------------------------------
        // Independent oracle: labels every owner's pieces at once (8- or 4-adjacency), no Core helper involved.

        internal sealed class Labeller
        {
            private static readonly int[] Di8 = { 1, -1, 0, 0, 1, -1, 1, -1 };
            private static readonly int[] Dj8 = { 0, 0, 1, -1, 1, 1, -1, -1 };

            public int[] Label;
            private int[] queue;
            public readonly List<byte> PieceOwner = new List<byte>();
            public readonly List<int> PieceSize = new List<int>();
            public readonly int[] PiecesOf = new int[256];

            /// <summary>Labels the pieces of every owner, or only of the owners flagged in include (null = all).</summary>
            public void Run(byte[] cells, int size, bool eight, bool[] include = null)
            {
                int total = cells.Length;
                if (Label == null || Label.Length != total)
                {
                    Label = new int[total];
                    queue = new int[total];
                }
                for (int c = 0; c < total; c++) Label[c] = -1;
                Array.Clear(PiecesOf, 0, PiecesOf.Length);
                PieceOwner.Clear();
                PieceSize.Clear();
                int dirs = eight ? 8 : 4;
                for (int c = 0; c < total; c++)
                {
                    byte o = cells[c];
                    if (o == OwnerGrid.Neutral || o == OwnerGrid.Void || Label[c] >= 0 || (include != null && !include[o])) continue;
                    int l = PieceOwner.Count;
                    PieceOwner.Add(o);
                    PiecesOf[o]++;
                    int head = 0, tail = 0;
                    Label[c] = l;
                    queue[tail++] = c;
                    while (head < tail)
                    {
                        int x = queue[head++];
                        int xi = x % size, xj = x / size;
                        for (int d = 0; d < dirs; d++)
                        {
                            int ni = xi + Di8[d], nj = xj + Dj8[d];
                            if (ni < 0 || nj < 0 || ni >= size || nj >= size) continue;
                            int nb = nj * size + ni;
                            if (Label[nb] >= 0 || cells[nb] != o) continue;
                            Label[nb] = l;
                            queue[tail++] = nb;
                        }
                    }
                    PieceSize.Add(tail);
                }
            }

            /// <summary>Cells of the owner outside its largest piece (the run must be current).</summary>
            public int CellsOutsideLargest(byte owner)
            {
                int largest = -1, sum = 0;
                for (int l = 0; l < PieceOwner.Count; l++)
                {
                    if (PieceOwner[l] != owner) continue;
                    sum += PieceSize[l];
                    if (largest < 0 || PieceSize[l] > PieceSize[largest]) largest = l;
                }
                return largest < 0 ? 0 : sum - PieceSize[largest];
            }

            public int Largest(byte owner)
            {
                int largest = -1;
                for (int l = 0; l < PieceOwner.Count; l++)
                {
                    if (PieceOwner[l] == owner && (largest < 0 || PieceSize[l] > PieceSize[largest])) largest = l;
                }
                return largest;
            }
        }

        // ------------------------------------------------------------------------------------------------------------
        // The report

        internal sealed class Report
        {
            public int Rounds, Checks, Ticks;
            public int Violations, StartViolations, FailedLinks;
            public int DiagonalNecks, DiagonalNecksVisible, DiagonalChecks;
            public int Links, Severances, Bridges;
            public readonly SortedDictionary<string, int> ByCause = new SortedDictionary<string, int>(StringComparer.Ordinal);
            public readonly SortedDictionary<string, int> NeckByCause = new SortedDictionary<string, int>(StringComparer.Ordinal);
            public readonly List<string> Samples = new List<string>();
            public double WallSeconds;

            public void Add(SortedDictionary<string, int> map, string cause)
            {
                map.TryGetValue(cause, out int count);
                map[cause] = count + 1;
            }

            public string Format(string title)
            {
                var sb = new StringBuilder();
                CultureInfo ci = CultureInfo.InvariantCulture;
                sb.Append(title).Append(": ").Append(Rounds).Append(" rounds, ").Append(Ticks).Append(" ticks, ").Append(Checks)
                  .Append(" grid checks, ").Append(WallSeconds.ToString("F1", ci)).Append(" s\n");
                sb.Append("  8-connectivity violations (new splits): ").Append(Violations).Append(" (start: ").Append(StartViolations)
                  .Append("), returns of a split player that captured nothing: ").Append(FailedLinks).Append('\n');
                foreach (KeyValuePair<string, int> kv in ByCause) sb.Append("    ").Append(kv.Value).Append("  ").Append(kv.Key).Append('\n');
                sb.Append("  diagonal-only connections (one 8-piece, several 4-pieces): ").Append(DiagonalNecks).Append(" new occurrences, ")
                  .Append(DiagonalNecksVisible).Append(" with a corner-joined part of at least ").Append(VisibleNeckCells).Append(" cells, ")
                  .Append(DiagonalChecks).Append(" player-checks with a corner neck\n");
                foreach (KeyValuePair<string, int> kv in NeckByCause) sb.Append("    ").Append(kv.Value).Append("  ").Append(kv.Key).Append('\n');
                sb.Append("  single-domain links ").Append(Links).Append(", single-domain severances ").Append(Severances)
                  .Append(", inheritance bridges ").Append(Bridges).Append('\n');
                for (int k = 0; k < Samples.Count; k++) sb.Append("  sample: ").Append(Samples[k]).Append('\n');
                return sb.ToString();
            }
        }

        /// <summary>A corner-joined part at least this big (cells) counts as a visible neck (2 x 2 u = 256 cells is a blob).</summary>
        internal const int VisibleNeckCells = 16;
        private const int MaxSamples = 40;

        /// <summary>
        /// Runs the round to its end. After every tick whose grid changed: every living player's territory must be one
        /// 8-connected piece (a new split is logged with its cause); corner-only connections are counted.
        /// </summary>
        internal static void RunRound(Simulation sim, string label, Report report)
        {
            OwnerGrid g = sim.Grid;
            int size = g.Size;
            int n = sim.Players.Count;
            var eight = new Labeller();
            var four = new Labeller();
            var before = (byte[])g.Cells.Clone();
            var split = new bool[n];
            var necked = new bool[n];
            var changed = new bool[256];
            var pocketPending = new bool[n];
            var events = new List<SimEvent>();
            sim.EventRaised += e =>
            {
                events.Add(e);
                if (e.Type == SimEventType.TerritorySevered && e.Other < 0) report.Severances++;
                if (e.Type == SimEventType.InheritanceBridged) report.Bridges++;
            };

            // Start territories.
            eight.Run(g.Cells, size, true);
            for (int i = 0; i < n; i++)
            {
                if (eight.PiecesOf[sim.Players[i].Id] > 1)
                {
                    split[i] = true;
                    report.Violations++;
                    report.StartViolations++;
                    report.Add(report.ByCause, "start territory in pieces");
                    if (report.Samples.Count < MaxSamples) report.Samples.Add(label + " start: player " + i + " owns " + eight.PiecesOf[sim.Players[i].Id] + " pieces");
                }
            }

            int version = g.Version;
            int linksBefore = 0;
            for (int i = 0; i < n; i++) linksBefore += sim.Players[i].DomainLinks;
            while (!sim.Ended)
            {
                events.Clear();
                sim.Step();
                report.Ticks++;
                string broken = BotTests.CheckInvariants(sim);
                if (broken != null) Assert.Fail(label + " tick " + sim.Tick + ": " + broken);

                // Returns of a player that was split before this tick and captured nothing: the link was not made.
                for (int k = 0; k < events.Count; k++)
                {
                    SimEvent e = events[k];
                    if (e.Type == SimEventType.LassoPocket) pocketPending[e.Player] = true;
                    if (e.Type == SimEventType.Return && split[e.Player] && !e.Chased && (e.Cells == null || e.Cells.Length == 0)) report.FailedLinks++;
                }

                if (g.Version != version)
                {
                    version = g.Version;
                    report.Checks++;
                    byte[] cells = g.Cells;
                    // Only the owners whose cells changed in this tick are labelled again (the others keep their state).
                    Array.Clear(changed, 0, changed.Length);
                    for (int c = 0; c < cells.Length; c++)
                    {
                        if (cells[c] == before[c]) continue;
                        changed[cells[c]] = true;
                        changed[before[c]] = true;
                    }
                    changed[OwnerGrid.Neutral] = false;
                    changed[OwnerGrid.Void] = false;
                    eight.Run(cells, size, true, changed);
                    bool anyEight = false;
                    for (int i = 0; i < n; i++)
                    {
                        PlayerState p = sim.Players[i];
                        if (!changed[p.Id] && p.Alive)
                        {
                            if (split[i]) anyEight = true;
                            continue;
                        }
                        bool now = p.Alive && eight.PiecesOf[p.Id] > 1;
                        if (now && !split[i])
                        {
                            report.Violations++;
                            string cause = Cause(sim, i, before, cells, events, pocketPending[i], eight);
                            report.Add(report.ByCause, cause);
                            if (report.Samples.Count < MaxSamples)
                            {
                                report.Samples.Add(label + " t=" + TraitTestKit.F(sim.Time) + " player " + i + ": " + eight.PiecesOf[p.Id]
                                                   + " pieces (" + eight.CellsOutsideLargest(p.Id) + " cells apart), cause: " + cause
                                                   + ", events: " + EventList(events));
                            }
                        }
                        split[i] = now;
                        if (now) anyEight = true;
                    }

                    four.Run(cells, size, false, changed);
                    for (int i = 0; i < n; i++)
                    {
                        PlayerState p = sim.Players[i];
                        if (!changed[p.Id] && p.Alive)
                        {
                            if (necked[i]) report.DiagonalChecks++;
                            continue;
                        }
                        bool neck = p.Alive && eight.PiecesOf[p.Id] == 1 && four.PiecesOf[p.Id] > 1;
                        if (neck)
                        {
                            report.DiagonalChecks++;
                            if (!necked[i])
                            {
                                report.DiagonalNecks++;
                                int apart = four.CellsOutsideLargest(p.Id);
                                if (apart >= VisibleNeckCells)
                                {
                                    report.DiagonalNecksVisible++;
                                    report.Add(report.NeckByCause, NeckCause(sim, i, before, cells, events));
                                }
                            }
                        }
                        necked[i] = neck;
                    }
                    _ = anyEight;
                    Buffer.BlockCopy(cells, 0, before, 0, cells.Length);
                }
                for (int k = 0; k < events.Count; k++)
                {
                    if (events[k].Type == SimEventType.Return || events[k].Type == SimEventType.Eliminated) pocketPending[events[k].Player] = false;
                }
            }
            int linksAfter = 0;
            for (int i = 0; i < n; i++) linksAfter += sim.Players[i].DomainLinks;
            report.Links += linksAfter - linksBefore;
            report.Rounds++;
        }

        private static string EventList(List<SimEvent> events)
        {
            var sb = new StringBuilder();
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                if (e.Type == SimEventType.Exit || e.Type == SimEventType.RingSpawned) continue;
                if (sb.Length > 0) sb.Append(", ");
                sb.Append(e.Type).Append('(').Append(e.Player).Append(',').Append(e.Other).Append(')');
                if (e.Cells != null) sb.Append('[').Append(e.Cells.Length).Append(']');
            }
            return sb.ToString();
        }

        /// <summary>
        /// The event that made player i's territory several pieces: the source of the cells of its non-largest pieces when
        /// they were gained in this tick, else who took the cells it lost in this tick.
        /// </summary>
        private static string Cause(Simulation sim, int i, byte[] before, byte[] after, List<SimEvent> events, bool pocket, Labeller eight)
        {
            byte id = sim.Players[i].Id;
            int largest = eight.Largest(id);
            int[] label = eight.Label;
            // A gain apart: a non-largest piece holding gained cells, or a piece made of gained cells only (a detached
            // capture can be larger than the old domain, which is then the non-largest piece).
            var hasOld = new Dictionary<int, bool>();
            bool gainedApart = false;
            for (int c = 0; c < after.Length; c++)
            {
                if (after[c] != id) continue;
                int l = label[c];
                bool old = before[c] == id;
                if (!old && l != largest) gainedApart = true;
                hasOld.TryGetValue(l, out bool seen);
                hasOld[l] = seen || old;
            }
            foreach (KeyValuePair<int, bool> kv in hasOld)
            {
                if (!kv.Value) gainedApart = true;
            }
            int returnsWithCells = 0;
            bool ownReturn = false;
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                if (e.Type == SimEventType.Return && e.Cells != null && e.Cells.Length > 0) returnsWithCells++;
                if (e.Type == SimEventType.Return && e.Player == i) ownReturn = true;
            }
            if (gainedApart)
            {
                for (int k = 0; k < events.Count; k++)
                {
                    SimEvent e = events[k];
                    if (e.Type == SimEventType.TerritoryInherited && e.Player == i) return "kill inheritance (island)";
                    if (e.Type == SimEventType.InheritanceBridged && e.Player == i) return "inheritance bridge band";
                    if (e.Type == SimEventType.TerritoryGrew && e.Player == i) return "trait: Propagation growth";
                    if (e.Type == SimEventType.TerritorySevered && e.Recipient == i) return "severed cells received (Capturer)";
                }
                if (ownReturn)
                {
                    if (returnsWithCells > 1) return "simultaneous returns (R18 contested cells left a detached gain)";
                    if (pocket) return "own return: detached lasso pocket";
                    return "own return: detached capture (region touching only the trail)";
                }
                return "own gain apart (unknown source)";
            }
            // The cells it lost in this tick and their new owners.
            int lostToPlayer = -1;
            bool lostToNeutral = false;
            for (int c = 0; c < after.Length; c++)
            {
                if (before[c] != id || after[c] == id) continue;
                if (after[c] == OwnerGrid.Neutral) lostToNeutral = true;
                else if (lostToPlayer < 0) lostToPlayer = after[c] - 1;
            }
            if (lostToPlayer >= 0)
            {
                string how = "capture";
                for (int k = 0; k < events.Count; k++)
                {
                    if (events[k].Type == SimEventType.InheritanceBridged && events[k].Player == lostToPlayer) how = "bridge band";
                }
                string suffix = ownReturn ? ", with its own simultaneous return" : "";
                return "enemy " + how + " split (v1.5 not applied" + suffix + ")";
            }
            if (lostToNeutral)
            {
                for (int k = 0; k < events.Count; k++)
                {
                    if (events[k].Type == SimEventType.TerritorySevered && events[k].Player == i) return "severance left several pieces";
                }
                return "cells lost to neutral (unknown source)";
            }
            return "unknown";
        }

        private static string NeckCause(Simulation sim, int i, byte[] before, byte[] after, List<SimEvent> events)
        {
            byte id = sim.Players[i].Id;
            bool gained = false, lost = false;
            for (int c = 0; c < after.Length; c++)
            {
                if (after[c] == id && before[c] != id) gained = true;
                if (before[c] == id && after[c] != id) lost = true;
            }
            for (int k = 0; k < events.Count; k++)
            {
                SimEvent e = events[k];
                if (gained && e.Type == SimEventType.TerritoryInherited && e.Player == i) return "kill inheritance";
                if (gained && e.Type == SimEventType.TerritoryGrew && e.Player == i) return "Propagation growth";
            }
            if (gained) return "own capture";
            if (lost) return "cells taken by a rival or severed";
            return "unknown";
        }

        // ------------------------------------------------------------------------------------------------------------
        // Matrices

        /// <summary>
        /// One round per (arena, set, lasso, lineup) cell of the matrix, seeds rotated so every cell of the matrix plays a
        /// different seed; rates rotated over 30 / 60 Hz to keep the dotnet loop fast.
        /// </summary>
        internal static Report RunMatrix(ArenaKind[] arenas, int seedsPerCell, ulong seedBase, Action<SimConfig> tweak, string title,
                                         bool halfCombos = false)
        {
            var report = new Report();
            var watch = Stopwatch.StartNew();
            int cell = 0;
            foreach (ArenaKind arena in arenas)
            {
                for (int set = 0; set < SetNames.Length; set++)
                {
                    for (int combo = 0; combo < 4; combo++)
                    {
                        // halfCombos: two of the four (lasso, lineup) combinations per set, alternating, so each arena still
                        // plays all four over its sets (lasso on + bots and lasso off + proxy, then the two others).
                        if (halfCombos && ((combo == 0 || combo == 3) != (set % 2 == 0))) continue;
                        bool lasso = (combo & 1) == 0;
                        bool proxy = (combo & 2) != 0;
                        for (int s = 0; s < seedsPerCell; s++)
                        {
                            ulong seed = seedBase + (ulong)(cell * seedsPerCell + s);
                            int rate = (cell + s) % 2 == 0 ? 30 : 60;
                            Simulation sim = BuildRound(seed, arena, set, lasso, proxy, rate, tweak);
                            string label = arena + "/" + SetNames[set] + "/lasso " + (lasso ? "on" : "off") + "/" + (proxy ? "proxy" : "bots")
                                           + "/seed " + seed + "/" + rate + " Hz";
                            RunRound(sim, label, report);
                        }
                        cell++;
                    }
                }
            }
            watch.Stop();
            report.WallSeconds = watch.Elapsed.TotalSeconds;
            TestContext.WriteLine(report.Format(title));
            return report;
        }

#if UNITY_5_3_OR_NEWER
        private static readonly ArenaKind[] FastArenas = { ArenaKind.Square };
#else
        private static readonly ArenaKind[] FastArenas = { ArenaKind.Square, ArenaKind.Croatia, ArenaKind.Greece };
#endif

        /// <summary>
        /// Rule v1.8 (contract 32): the stress invariant in the dotnet loop. Square, Croatia and Greece x classic and the
        /// three v1.1 biome sets x two of the four (lasso on / off, bot-only / human proxy) combinations per set, all four
        /// per arena: 24 full rounds at 30 or 60 Hz (Unity: the square arena only, 8 rounds). Zero living player ever owns
        /// two separate pieces after a tick.
        /// </summary>
        [Test]
        public void R23_EveryLivingTerritoryIsOneEightConnectedPieceAfterEveryTick()
        {
            Report r = RunMatrix(FastArenas, 1, 1UL, null, "Single domain stress (default rules)", true);
            Assert.That(r.Rounds, Is.GreaterThanOrEqualTo(8));
            Assert.AreEqual(0, r.Violations, r.Format("violations"));
            Assert.AreEqual(0, r.FailedLinks, "a return joining separate pieces always links them");
        }

        /// <summary>The bigger variant: five arenas, three seeds per matrix cell (240 rounds). Report only plus the invariant.</summary>
        [Test, Explicit, Category("Stress")]
        public void R23_Stress_FiveArenasThreeSeedsPerCell()
        {
            Report r = RunMatrix(new[] { ArenaKind.Square, ArenaKind.Croatia, ArenaKind.Greece, ArenaKind.Italy, ArenaKind.Norway }, 3, 1000UL, null,
                                 "Single domain stress, big (default rules)");
            Assert.AreEqual(0, r.Violations, r.Format("violations"));
        }

        /// <summary>Diagnosis only: the same big matrix with the pre-v1.8 rules (SimConfig.SingleDomain = Off).</summary>
        [Test, Explicit, Category("Stress")]
        public void R23_Diagnosis_PreV18Rules()
        {
            RunMatrix(new[] { ArenaKind.Square, ArenaKind.Croatia, ArenaKind.Greece, ArenaKind.Italy, ArenaKind.Norway }, 3, 1000UL,
                      c => c.SingleDomain = SingleDomainRule.Off, "Single domain stress, big (pre-v1.8 rules: SingleDomain = Off)");
        }

        /// <summary>Diagnosis only: the fast matrix with the pre-v1.8 rules.</summary>
        [Test, Explicit, Category("Stress")]
        public void R23_Diagnosis_PreV18RulesFastMatrix()
        {
            RunMatrix(FastArenas, 1, 1UL, c => c.SingleDomain = SingleDomainRule.Off, "Single domain stress (pre-v1.8 rules: SingleDomain = Off)", true);
        }
    }
}
