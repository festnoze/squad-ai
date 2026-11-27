// Owned by B5. Contract 16: Haptics.Pulse(int ms) never throws. Android only (a no-op elsewhere, the editor included):
// it returns at once when SaveData.HapticsOn is false, and drives the Android Vibrator through AndroidJavaObject
// (VibrationEffect.createOneShot when API >= 26, the deprecated vibrate(long) before). Every JNI call is wrapped in
// try/catch: the first failure logs once (warning) and disables haptics for the rest of the run.
// The unreachable Handheld.Vibrate() reference inside AndroidPulse (a method that Pulse calls on Android) makes Unity add
// android.permission.VIBRATE to the manifest; Builder also checks the permission (contract 17).
using System;
using UnityEngine;

namespace PainterIO.Runtime
{
    public static class Haptics
    {
        /// <summary>Contract 16 durations (ms).</summary>
        public const int CutReceivedMs = 60;
        public const int CutDealtMs = 30;

        /// <summary>The human is caught by the spark, or eliminated by territory loss (wave C, feel-13).</summary>
        public const int CaughtMs = 120;
        public const int SavedReturnMs = 40;
        public const int CaptureMs = 20;

        /// <summary>Longest pulse accepted; longer requests are clamped.</summary>
        public const int MaxPulseMs = 1000;

        private static bool s_Disabled;

        /// <summary>True once a JNI call failed: haptics stay off for the rest of the run.</summary>
        public static bool Disabled => s_Disabled;

        /// <summary>Vibrates for ms milliseconds on Android when SaveData.HapticsOn; a no-op elsewhere. Never throws.</summary>
        public static void Pulse(int ms)
        {
            try
            {
#if UNITY_ANDROID && !UNITY_EDITOR
                AndroidPulse(ms);
#endif
            }
            catch (Exception e)
            {
                Disable("Pulse", e);
            }
        }

        private static void Disable(string what, Exception e)
        {
            if (s_Disabled) return;
            s_Disabled = true;
            try
            {
                Debug.LogWarning("[PainterIO] Haptics disabled: " + what + " failed: " + (e != null ? e.Message : "?"));
            }
            catch (Exception)
            {
                // Logging must never make Pulse throw.
            }
        }

#if UNITY_ANDROID || UNITY_EDITOR
        // Compiled in the editor too (so a type error shows up in every compile), called only by Android players.
        private const int DefaultAmplitude = -1;   // VibrationEffect.DEFAULT_AMPLITUDE

#pragma warning disable 0649
        // Never assigned: only there so the Handheld.Vibrate() reference below exists in a called method (contract 16).
        private static bool s_NeverTrue;
#pragma warning restore 0649

        private static bool s_Initialized;
        private static int s_Sdk;
        private static AndroidJavaObject s_Vibrator;
        private static AndroidJavaClass s_EffectClass;

        private static void AndroidPulse(int ms)
        {
            if (s_NeverTrue) Handheld.Vibrate();   // unreachable on purpose: adds android.permission.VIBRATE (contract 16)
            if (s_Disabled || !SaveData.HapticsOn || ms <= 0) return;
            if (ms > MaxPulseMs) ms = MaxPulseMs;
            if (!s_Initialized)
            {
                s_Initialized = true;
                if (!AndroidInit()) return;
            }
            if (s_Vibrator == null) return;
            if (s_Sdk >= 26 && s_EffectClass != null)
            {
                AndroidJavaObject effect = null;
                try
                {
                    effect = s_EffectClass.CallStatic<AndroidJavaObject>("createOneShot", (long)ms, DefaultAmplitude);
                    s_Vibrator.Call("vibrate", effect);
                }
                catch (Exception e)
                {
                    Disable("vibrate(VibrationEffect)", e);
                }
                finally
                {
                    if (effect != null)
                    {
                        try
                        {
                            effect.Dispose();
                        }
                        catch (Exception)
                        {
                            // Releasing a local reference cannot be retried; ignore.
                        }
                    }
                }
            }
            else
            {
                try
                {
                    s_Vibrator.Call("vibrate", (long)ms);
                }
                catch (Exception e)
                {
                    Disable("vibrate(long)", e);
                }
            }
        }

        private static bool AndroidInit()
        {
            try
            {
                using (var version = new AndroidJavaClass("android.os.Build$VERSION"))
                {
                    s_Sdk = version.GetStatic<int>("SDK_INT");
                }
                using (var player = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                using (AndroidJavaObject activity = player.GetStatic<AndroidJavaObject>("currentActivity"))
                {
                    s_Vibrator = activity != null ? activity.Call<AndroidJavaObject>("getSystemService", "vibrator") : null;
                }
                if (s_Vibrator != null && !s_Vibrator.Call<bool>("hasVibrator"))
                {
                    s_Vibrator.Dispose();
                    s_Vibrator = null;
                }
                if (s_Vibrator != null && s_Sdk >= 26) s_EffectClass = new AndroidJavaClass("android.os.VibrationEffect");
                return s_Vibrator != null;
            }
            catch (Exception e)
            {
                s_Vibrator = null;
                s_EffectClass = null;
                Disable("Vibrator lookup", e);
                return false;
            }
        }
#endif
    }
}
