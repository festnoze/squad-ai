// Owned by B0a. Contract 11.2: fixed-step accumulator that drives a Simulation from frame deltas, frame-rate independent.
using System;
using PainterIO.Core;

namespace PainterIO.Runtime
{
    /// <summary>
    /// Steps a Simulation at its own TickRate whatever the display rate. Frame deltas (scaled by TimeScale) accumulate in
    /// double; Advance steps while the accumulator holds a whole tick, at most MaxStepsPerFrame times (the rest of a long
    /// hitch is dropped, keeping the sub-tick phase). The outcome depends only on the number of ticks, never on the frame
    /// deltas (contract 10.1 S4-Display).
    /// </summary>
    public sealed class SimRunner
    {
        public const int MaxStepsPerFrame = 8;

        public bool Paused;
        public float TimeScale = 1f;

        private readonly Simulation sim;
        private readonly double dt;
        private double accumulator;

        public SimRunner(Simulation sim)
        {
            this.sim = sim ?? throw new ArgumentNullException(nameof(sim));
            dt = sim.Config.Dt;
        }

        /// <summary>The simulation this runner steps.</summary>
        public Simulation Sim => sim;

        /// <summary>Raised after each Sim.Step inside Advance (GameSession forwards the step's events from here).</summary>
        public event Action<Simulation> Stepped;

        /// <summary>Ticks stepped by this runner since it was created.</summary>
        public long StepsTaken { get; private set; }

        /// <summary>Accumulates deltaTime x TimeScale and steps the sim while a whole tick is available (max 8); returns the steps.</summary>
        public int Advance(float deltaTime)
        {
            if (Paused || sim.Ended) return 0;
            if (!(deltaTime > 0f) || float.IsInfinity(deltaTime)) return 0;
            float scale = TimeScale;
            if (!(scale > 0f) || float.IsInfinity(scale)) return 0;

            accumulator += (double)deltaTime * scale;
            int steps = 0;
            while (accumulator >= dt && steps < MaxStepsPerFrame && !Paused && !sim.Ended)
            {
                accumulator -= dt;
                sim.Step();
                steps++;
                StepsTaken++;
                Stepped?.Invoke(sim);
            }
            if (accumulator >= dt)
            {
                // Too slow to keep up (or paused / ended mid-frame): drop whole ticks, keep the phase.
                accumulator -= Math.Floor(accumulator / dt) * dt;
            }
            return steps;
        }

        /// <summary>accumulator / dt in [0, 1]: interpolation factor between PrevPos and Pos (1 once the round ended).</summary>
        public float Alpha
        {
            get
            {
                if (sim.Ended) return 1f;
                double a = accumulator / dt;
                return a <= 0.0 ? 0f : (a >= 1.0 ? 1f : (float)a);
            }
        }
    }
}
