// Owned by BI (wave B-2). Contract 25.2: BiomeFx hosts the current biome's extra effects component (LiquidFx, FireFx or
// ElectricFx: embers, smoke puffs, arcs...). The host follows GameDirector (SessionStarted, StateChanged) and
// BiomeTheme.Changed: when the biome changes it destroys the old effects component and adds the new one, then hands it
// the bound session and forwards every sim event to it. Each biome agent only edits its own *Fx.cs file.
//
// Budget (contract 25.5): at most 200 extra particles per biome, code-built meshes or ParticleSystem with materials from
// the biome's Overlay shader (BiomeTheme.Current.ResolveOverlay()), never Shader.Find.
using System;
using PainterIO.Core;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class BiomeFx
    {
        /// <summary>Contract 11.1-style entry point: the BiomeFx root (the host component), following the current biome.</summary>
        public static Component Create(GameDirector d)
        {
            var go = new GameObject("BiomeFx");
            var host = go.AddComponent<BiomeFxHost>();
            host.Initialize(d);
            return host;
        }

        /// <summary>The effects component type of a biome.</summary>
        public static Type ComponentTypeOf(BiomeId id)
        {
            switch (id)
            {
                case BiomeId.Fire: return typeof(FireFx);
                case BiomeId.Electric: return typeof(ElectricFx);
                default: return typeof(LiquidFx);
            }
        }
    }

    /// <summary>
    /// Base of the per-biome effects components. The host calls Attach once after AddComponent, Bind on every session
    /// (attract restarts included), OnSimEvent for every forwarded sim event and OnStateChanged on GameDirector state
    /// changes. Every call runs inside the host's try/catch (logged once per component).
    /// </summary>
    public abstract class BiomeFxBehaviour : MonoBehaviour
    {
        public abstract BiomeId Biome { get; }

        public GameDirector Director { get; private set; }

        /// <summary>The bound session (null between sessions).</summary>
        public GameSession Session { get; private set; }

        /// <summary>Theme of this component's biome.</summary>
        public BiomeTheme Theme => BiomeTheme.Get(Biome);

        internal void Attach(GameDirector director)
        {
            Director = director;
            OnAttached();
        }

        internal void Bind(GameSession session)
        {
            Session = session;
            OnBind(session);
        }

        /// <summary>Called once, right after the host added the component.</summary>
        protected virtual void OnAttached() { }

        /// <summary>A session started (also an attract restart): reset the effects.</summary>
        protected virtual void OnBind(GameSession session) { }

        /// <summary>A sim event of the bound session (forwarded after each Step, in resolution order).</summary>
        public virtual void OnSimEvent(SimEvent e) { }

        /// <summary>GameDirector changed state.</summary>
        public virtual void OnStateChanged(GameState state) { }
    }

    /// <summary>The host of the current biome's effects component (BiomeFx.Create builds it).</summary>
    public sealed class BiomeFxHost : MonoBehaviour
    {
        private GameDirector director;
        private GameSession session;
        private BiomeFxBehaviour active;
        private bool errorLogged;

        /// <summary>The effects component of the current biome (null if it failed to build).</summary>
        public BiomeFxBehaviour Active => active;

        internal void Initialize(GameDirector d)
        {
            director = d;
            BiomeTheme.Changed += OnBiomeChanged;
            if (d != null)
            {
                d.SessionStarted += OnSessionStarted;
                d.StateChanged += OnStateChanged;
            }
            Swap(BiomeTheme.Current.Id);
            if (d != null && d.Session != null) OnSessionStarted(d.Session);
        }

        private void OnDestroy()
        {
            Teardown();
        }

        /// <summary>Unsubscribes everything (OnDestroy calls it; edit-mode tests call it before DestroyImmediate).</summary>
        public void Teardown()
        {
            BiomeTheme.Changed -= OnBiomeChanged;
            if (director != null)
            {
                director.SessionStarted -= OnSessionStarted;
                director.StateChanged -= OnStateChanged;
            }
            if (session != null) session.EventRaised -= OnSimEvent;
            session = null;
        }

        private void OnBiomeChanged(BiomeTheme theme)
        {
            if (this == null)
            {
                BiomeTheme.Changed -= OnBiomeChanged;   // destroyed in edit mode without OnDestroy
                return;
            }
            if (theme == null) return;
            if (active != null && active.Biome == theme.Id) return;
            Swap(theme.Id);
            if (active != null) Guard(() => active.Bind(session));
        }

        private void Swap(BiomeId id)
        {
            if (active != null)
            {
                BiomeFxBehaviour old = active;
                active = null;
                if (Application.isPlaying) Destroy(old);
                else DestroyImmediate(old);
            }
            try
            {
                active = (BiomeFxBehaviour)gameObject.AddComponent(BiomeFx.ComponentTypeOf(id));
                active.Attach(director);
            }
            catch (Exception e)
            {
                Debug.LogError("[PainterIO] BiomeFx " + id + " failed: " + e);
                active = null;
            }
        }

        private void OnSessionStarted(GameSession s)
        {
            if (session != null) session.EventRaised -= OnSimEvent;
            session = s;
            if (s != null)
            {
                s.EventRaised -= OnSimEvent;
                s.EventRaised += OnSimEvent;
            }
            if (active != null) Guard(() => active.Bind(s));
        }

        private void OnStateChanged(GameState state)
        {
            if (active != null) Guard(() => active.OnStateChanged(state));
        }

        private void OnSimEvent(SimEvent e)
        {
            if (active != null) Guard(() => active.OnSimEvent(e));
        }

        private void Guard(Action action)
        {
            try
            {
                action();
            }
            catch (Exception e)
            {
                if (errorLogged) return;
                errorLogged = true;
                Debug.LogError("[PainterIO] BiomeFx " + (active != null ? active.Biome.ToString() : "?") + " failed: " + e);
            }
        }
    }
}
