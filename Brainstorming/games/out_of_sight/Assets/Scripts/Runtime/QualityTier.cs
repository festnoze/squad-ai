using System;
using OutOfSight.Core;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace OutOfSight
{
    /// <summary>
    /// M7 (docs/CONTRACT_M7.md 1.3 and 1.4): the Qualité option applied at once. ProjectSetup writes three levels in
    /// QualitySettings: Bas and Moyen on Mobile_RPAsset (hard shadows only, no SSAO on Mobile_Renderer) and Haut on
    /// PC_RPAsset (the PC look). Bas and Moyen share their URP asset, so what tells them apart is applied here: the
    /// render scale written on that shared asset (0.75 on Bas, 1 otherwise, so leaving Bas always restores it) and
    /// the bloom, turned off on Bas by a global volume of higher priority that overrides its intensity to 0 (the
    /// look's own profile is never touched). On a mobile platform the target frame rate follows the tier (30 on Bas
    /// and Moyen, 60 on Haut) and the screen never sleeps; on PC the frame rate setting is left as it is.
    /// SaveStore applies it after every load and options change. Play mode only: EditMode tests apply nothing.
    /// </summary>
    public static class QualityTier
    {
        /// <summary>The level names in QualitySettings (ProjectSetup writes them in this order).</summary>
        public const string LevelLow = "Bas";
        public const string LevelMedium = "Moyen";
        public const string LevelHigh = "Haut";

        private static GameObject bloomOff;

        /// <summary>The tier applied last ("low", "medium" or "high"), null before the first apply.</summary>
        public static string Applied { get; private set; }

        /// <summary>True while the Bas volume that turns bloom off is in the scene.</summary>
        public static bool BloomSuppressed => bloomOff != null;

        /// <summary>The bloom override volume of Bas (tests), or null.</summary>
        public static Volume BloomOffVolume => bloomOff != null ? bloomOff.GetComponent<Volume>() : null;

        /// <summary>The render scale of the URP asset in use (tests), or -1 when the pipeline is not URP.</summary>
        public static float ActiveRenderScale =>
            GraphicsSettings.currentRenderPipeline is UniversalRenderPipelineAsset urp ? urp.renderScale : -1f;

        /// <summary>
        /// True when the bloom that every volume in the scene blends to, as seen from <paramref name="camera"/>, is on
        /// (tests: the volume stack is updated here, not left to the next rendered frame).
        /// </summary>
        public static bool BloomReaches(Camera camera)
        {
            // The pipeline, and with it the volume manager, is (re)created by the first render after a quality switch
            // (and a batch mode editor renders nothing by itself): one small render of the camera makes sure of it.
            RenderTexture rt = RenderTexture.GetTemporary(64, 64, 24);
            var request = new RenderPipeline.StandardRequest { destination = rt };
            if (RenderPipeline.SupportsRenderRequest(camera, request))
            {
                RenderPipeline.SubmitRenderRequest(camera, request);
            }
            RenderTexture.ReleaseTemporary(rt);
            if (!VolumeManager.instance.isInitialized)
            {
                throw new InvalidOperationException("the volume manager is not initialized after a render");
            }
            VolumeStack stack = VolumeManager.instance.stack;
            LayerMask mask = camera.GetUniversalAdditionalCameraData().volumeLayerMask;
            VolumeManager.instance.Update(stack, camera.transform, mask);
            Bloom bloom = stack.GetComponent<Bloom>();
            return bloom != null && bloom.IsActive();
        }

        /// <summary>The QualitySettings level name of a tier.</summary>
        public static string LevelName(string quality)
        {
            return quality == SaveOptions.QualityLow ? LevelLow : quality == SaveOptions.QualityMedium ? LevelMedium : LevelHigh;
        }

        /// <summary>The Android target frame rate of a tier: 60 on Haut, 30 below.</summary>
        public static int TargetFrameRate(string quality)
        {
            return quality == SaveOptions.QualityHigh ? Tuning.QualityHighFrameRate : Tuning.QualityLowFrameRate;
        }

        /// <summary>Applies the tier the options ask for (the platform default when they hold none). Never throws.</summary>
        public static void Apply(SaveOptions options)
        {
            if (!Application.isPlaying)
            {
                return;
            }
            try
            {
                ApplyCore((options ?? SaveOptions.Default()).QualityFor(Application.isMobilePlatform));
            }
            catch (Exception e)
            {
                Debug.LogWarning("[QualityTier] cannot apply the quality: " + e.Message);
            }
        }

        private static void ApplyCore(string quality)
        {
            string[] names = QualitySettings.names;
            int index = Array.IndexOf(names, LevelName(quality));
            if (index < 0)
            {
                Debug.LogWarning($"[QualityTier] no quality level named {LevelName(quality)} (run OutOfSight/Project Setup)");
                return;
            }
            if (QualitySettings.GetQualityLevel() != index)
            {
                QualitySettings.SetQualityLevel(index, true);
            }
            int low = Array.IndexOf(names, LevelLow);
            if (low >= 0 && QualitySettings.GetRenderPipelineAssetAt(low) is UniversalRenderPipelineAsset lowAsset)
            {
                // Shared with Moyen: back to 1 whenever the tier is not Bas.
                lowAsset.renderScale = quality == SaveOptions.QualityLow ? Tuning.QualityLowRenderScale : Tuning.QualityMediumRenderScale;
            }
            SetBloomOff(quality == SaveOptions.QualityLow); // MUTATION:QUALITY_LOW_BLOOM
            // Floor dust (docs/m9/FLOORS_WALLS.md section 10): Haut only; Bas and Moyen build no map and draw no dust.
            FloorDust.SetTier(quality == SaveOptions.QualityHigh); // MUTATION:FLOOR_DUST_TIER
            if (Application.isMobilePlatform)
            {
                Application.targetFrameRate = TargetFrameRate(quality);
                // CONTRACT_M7 1.3: the screen never dims while the game runs.
                Screen.sleepTimeout = SleepTimeout.NeverSleep;
            }
            Applied = quality;
        }

        private static void SetBloomOff(bool off)
        {
            if (!off)
            {
                if (bloomOff != null)
                {
                    UnityEngine.Object.Destroy(bloomOff);
                }
                bloomOff = null;
                return;
            }
            if (bloomOff != null)
            {
                return;
            }
            bloomOff = new GameObject("QualityBloomOff");
            // Under Main when there is one: it then goes with the scene Main belongs to, and the next Main's
            // SaveStore.Boot applies the tier again.
            if (Main.Instance != null)
            {
                bloomOff.transform.SetParent(Main.Instance.transform, false);
            }
            var volume = bloomOff.AddComponent<Volume>();
            volume.isGlobal = true;
            volume.priority = Tuning.QualityVolumePriority;
            VolumeProfile profile = ScriptableObject.CreateInstance<VolumeProfile>();
            profile.name = "OutOfSight Quality Bas";
            Bloom bloom = profile.Add<Bloom>(false);
            bloom.intensity.Override(0f);
            volume.sharedProfile = profile;
        }
    }
}
