using System.Collections.Generic;
using Meuble.Core;
using UnityEngine;

namespace Meuble
{
    /// <summary>
    /// The floor lamp's light (docs/CONTRACT_M4.md 2.3, amendments 9.3 and 9.12). An unshadowed point light at
    /// the top of the lamp body: PRD 7.4 and the M3 look keep exactly one shadowed light, the sun.
    ///
    /// Switched off, the light goes out and the lamp's room is dimmed by the lamp itself (rooms are visual
    /// only, and Main is not involved): every point or spot light standing in that room drops to
    /// <see cref="Tuning.LampOffLight"/> of its intensity, and the ambient light drops to
    /// <see cref="AmbientOffFactor"/>. The ambient is global in URP, so it is the nearest thing to "the room
    /// ambient"; it is restored exactly when the lamp is switched on again or destroyed (a restart, a new level).
    ///
    /// The rule part is <see cref="RangeFactor"/>: what every inhabitant's range is multiplied by for the lamp's
    /// own sample points (FurnitureController.SightRangeFactor, Vision.Step).
    /// </summary>
    public sealed class LampLight : MonoBehaviour
    {
        // Not in Tuning (presentation only, the rules never read them).
        // The bulb sits this far below the top of the lamp body, inside the shade.
        private const float BulbBelowTop = 0.25f;
        // A floor lamp lights its corner of a room, not the whole house.
        private const float LightRange = 4f;
        private const float LightIntensity = 1.6f;
        private static readonly Color LightColor = new Color(1f, 0.82f, 0.56f);
        // The share of the ambient light left while the lamp is off: dark enough to read, never black.
        private const float AmbientOffFactor = 0.6f;

        public bool On { get; private set; } = true;

        /// <summary>Factor applied to ViewRange for the lamp's own sample points.</summary>
        public float RangeFactor => On ? 1f : Tuning.LampOffLight; // MUTATION:LAMP_RANGE

        /// <summary>The point light (null before <see cref="Init"/>).</summary>
        public Light Light { get; private set; }

        /// <summary>True while this lamp holds the ambient and its room lights dimmed.</summary>
        public bool Dimming { get; private set; }

        // The ambient as it was before the first lamp dimmed it (static: restored by the last lamp to switch on).
        private static int dimmers;
        private static Color savedSky;
        private static Color savedEquator;
        private static Color savedGround;
        private static Color savedAmbient;

        private readonly List<(Light light, float intensity)> dimmedLights = new List<(Light, float)>();
        private RoomDef dimmedRoom;

        /// <summary>Builds the point light at the top of a lamp body of <paramref name="height"/>. Idempotent.</summary>
        public void Init(float height)
        {
            if (Light == null)
            {
                Light = gameObject.GetComponent<Light>();
            }
            if (Light == null)
            {
                Light = gameObject.AddComponent<Light>();
            }
            Light.type = LightType.Point;
            Light.shadows = LightShadows.None;
            Light.range = LightRange;
            Light.intensity = LightIntensity;
            Light.color = LightColor;
            Light.renderMode = LightRenderMode.ForcePixel;
            transform.localPosition = new Vector3(0f, Mathf.Max(0.1f, height - BulbBelowTop), 0f);
            transform.localRotation = Quaternion.identity;
            Apply();
        }

        public void Toggle()
        {
            SetOn(!On);
        }

        /// <summary>Switches the lamp on or off (the rules, the light and the room dimming).</summary>
        public void SetOn(bool on)
        {
            if (on == On)
            {
                return;
            }
            On = on;
            Apply();
        }

        private void Apply()
        {
            if (Light != null)
            {
                Light.enabled = On;
            }
            if (On)
            {
                Undim();
            }
            else
            {
                Dim();
            }
        }

        private void LateUpdate()
        {
            // The darkness follows the lamp: carried into another room while off, it dims that room instead.
            if (Dimming && RoomOf(transform.position) != dimmedRoom)
            {
                RestoreRoomLights();
                DimRoomLights();
            }
        }

        private void Dim()
        {
            if (Dimming)
            {
                return;
            }
            Dimming = true;
            if (dimmers++ == 0)
            {
                savedSky = RenderSettings.ambientSkyColor;
                savedEquator = RenderSettings.ambientEquatorColor;
                savedGround = RenderSettings.ambientGroundColor;
                savedAmbient = RenderSettings.ambientLight;
                RenderSettings.ambientSkyColor = savedSky * AmbientOffFactor;
                RenderSettings.ambientEquatorColor = savedEquator * AmbientOffFactor;
                RenderSettings.ambientGroundColor = savedGround * AmbientOffFactor;
                RenderSettings.ambientLight = savedAmbient * AmbientOffFactor;
            }
            DimRoomLights();
        }

        private void Undim()
        {
            if (!Dimming)
            {
                return;
            }
            Dimming = false;
            RestoreRoomLights();
            if (--dimmers <= 0)
            {
                dimmers = 0;
                RenderSettings.ambientSkyColor = savedSky;
                RenderSettings.ambientEquatorColor = savedEquator;
                RenderSettings.ambientGroundColor = savedGround;
                RenderSettings.ambientLight = savedAmbient;
            }
        }

        private void DimRoomLights()
        {
            dimmedRoom = RoomOf(transform.position);
            if (dimmedRoom == null)
            {
                return;
            }
            foreach (Light l in FindObjectsByType<Light>(FindObjectsSortMode.None))
            {
                if (l == null || l == Light || !l.enabled || l.type == LightType.Directional)
                {
                    continue;
                }
                Vector3 p = l.transform.position;
                if (dimmedRoom.Contains(p))
                {
                    dimmedLights.Add((l, l.intensity));
                    l.intensity *= Tuning.LampOffLight;
                }
            }
        }

        private void RestoreRoomLights()
        {
            foreach ((Light l, float intensity) in dimmedLights)
            {
                if (l != null)
                {
                    l.intensity = intensity;
                }
            }
            dimmedLights.Clear();
            dimmedRoom = null;
        }

        /// <summary>The room of the level being played that contains <paramref name="p"/>, or null (no level, edit mode).</summary>
        private static RoomDef RoomOf(Vector3 p)
        {
            LevelDef def = Main.Instance != null && Main.Instance.Game != null ? Main.Instance.Game.Def : null;
            return def?.RoomAt(p);
        }

        private void OnDisable()
        {
            Undim();
        }

        private void OnEnable()
        {
            if (!On)
            {
                Dim();
            }
        }

        private void OnDestroy()
        {
            Undim();
        }
    }
}
