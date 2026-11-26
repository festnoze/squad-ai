using System.Collections.Generic;
using NUnit.Framework;
using OutOfSight.Core;
using UnityEditor;
using UnityEngine;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Room lighting on Haut (2026-11-20): the High tier's renderer (PC_Renderer, PC_RPAsset) carries the tuned SSAO that
    /// darkens the junctions (wall and floor, wall corners, furniture contact), the Bas and Moyen renderer (Mobile_Renderer)
    /// still carries none, and the title ceiling's Haut contact shade falls off from the walls to the middle of a room.
    /// The renderer assets are read through SerializedObject (the SSAO settings are internal to URP and this assembly does not
    /// reference the URP runtime); the expected values are ProjectSetup's (SsaoIntensity and the rest), which writes them.
    /// </summary>
    public sealed class LightingHighTests
    {
        private const string PcRenderer = "Assets/Settings/PC_Renderer.asset";
        private const string MobileRenderer = "Assets/Settings/Mobile_Renderer.asset";

        private static Object Ssao(string path)
        {
            foreach (Object o in AssetDatabase.LoadAllAssetsAtPath(path))
            {
                if (o != null && o.GetType().Name == "ScreenSpaceAmbientOcclusion")
                {
                    return o;
                }
            }
            return null;
        }

        [Test]
        public void The_High_renderer_shades_the_junctions_with_the_tuned_SSAO()
        {
            Object ssao = Ssao(PcRenderer);
            Assert.IsNotNull(ssao, "PC_Renderer has no SSAO feature");
            var so = new SerializedObject(ssao);
            Assert.IsTrue(so.FindProperty("m_Active").boolValue, "the SSAO feature is inactive");
            SerializedProperty s = so.FindProperty("m_Settings");
            Assert.IsNotNull(s, "SSAO m_Settings not found");
            // ProjectSetup.SsaoIntensity, SsaoRadius, SsaoDirectLighting: a room-scale radius, so a wall and floor junction and a
            // wall corner darken over a hand's breadth, not just the furniture's contact line (the M3 values were 0.6, 0.3, 0.25).
            Assert.AreEqual(1.6f, s.FindPropertyRelative("Intensity").floatValue, 1e-4f, "intensity");
            Assert.AreEqual(0.7f, s.FindPropertyRelative("Radius").floatValue, 1e-4f, "radius");
            Assert.AreEqual(0.6f, s.FindPropertyRelative("DirectLightingStrength").floatValue, 1e-4f, "direct lighting strength");
            // Interleaved gradient noise: blue noise left a visible grain in the corners at the title's close eye level camera.
            Assert.AreEqual(1, s.FindPropertyRelative("AOMethod").intValue, "noise method (1: interleaved gradient)");
            Assert.AreEqual(0, s.FindPropertyRelative("Samples").intValue, "samples (0: high, 12)");
            Assert.AreEqual(0, s.FindPropertyRelative("BlurQuality").intValue, "blur (0: bilateral)");
            Assert.AreEqual(1, s.FindPropertyRelative("Source").intValue, "source (1: depth normals)");
            // Applied in the lighting, never multiplied over the image (that drew black halos round the furniture).
            Assert.IsFalse(s.FindPropertyRelative("AfterOpaque").boolValue, "after opaque");
            Assert.IsFalse(s.FindPropertyRelative("Downsample").boolValue, "downsample");
        }

        [Test]
        public void Bas_and_Moyen_keep_a_renderer_without_SSAO()
        {
            Assert.IsNull(Ssao(MobileRenderer), "Mobile_Renderer (Bas and Moyen, the Android default) gained an SSAO feature");
        }

        [Test]
        public void The_title_ceiling_shade_is_darkest_in_the_corners_and_fades_to_nothing_mid_room()
        {
            var room = new RoomDef { X = 2f, Z = 2.5f, SizeX = 4f, SizeZ = 5f, WallHeight = 2.7f, WallThickness = 0.1f };
            var rooms = new List<RoomDef> { room };
            float shade = TitleCameraTour.CeilingShade;
            float reach = TitleCameraTour.CeilingShadeReach;
            float centre = TitleCameraTour.CeilingShadeAt(rooms, 2f, 2.5f, shade, reach);
            // At a wall face (half a thickness inside the room's side), midway along it.
            float wall = TitleCameraTour.CeilingShadeAt(rooms, 0.05f, 2.5f, shade, reach);
            float corner = TitleCameraTour.CeilingShadeAt(rooms, 0.05f, 0.05f, shade, reach);
            float inWall = TitleCameraTour.CeilingShadeAt(rooms, -0.02f, 2.5f, shade, reach);
            Assert.Greater(centre, 0.99f, "the middle of the room is shaded");
            Assert.AreEqual(1f - shade, wall, 0.02f, "the shade at a wall face");
            Assert.AreEqual((1f - shade) * (1f - shade), corner, 0.02f, "a corner takes the shade of both walls");
            Assert.Less(corner, wall, "the corner is not darker than the wall line");
            Assert.AreEqual(1f - shade, inWall, 1e-5f, "inside a wall");
            float previous = wall;
            for (float x = 0.15f; x <= 2f; x += 0.1f)
            {
                float v = TitleCameraTour.CeilingShadeAt(rooms, x, 2.5f, shade, reach);
                Assert.GreaterOrEqual(v, previous - 1e-5f, $"the shade grows darker away from the wall at x {x:0.00}");
                previous = v;
            }
            Assert.Greater(shade, 0.2f, "premise: a visible shade");
            Assert.Less(shade, 0.6f, "premise: the ceiling never goes black at a wall");
        }
    }
}
