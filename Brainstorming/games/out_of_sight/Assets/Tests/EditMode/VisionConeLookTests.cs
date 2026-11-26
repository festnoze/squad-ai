using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace OutOfSight.Tests
{
    /// <summary>
    /// Cones look (product owner request, 2026-11-20): the vision cone shader is created from code
    /// (VisionConeView.ConeMaterial), and a shader only named in code is stripped from the player. It ships twice over:
    /// XRay_Cone.mat (the x-ray cone pass's override material, referenced by both renderers) uses it in its hatched mode,
    /// and ProjectSetup lists it in Always Included Shaders. Both are checked here on the project files ProjectSetup wrote.
    /// </summary>
    public sealed class VisionConeLookTests
    {
        [Test]
        public void The_cone_shader_ships_with_the_player()
        {
            Shader shader = Shader.Find(VisionConeView.ConeShaderName);
            Assert.IsNotNull(shader, "the vision cone shader is not in the project");

            var xray = AssetDatabase.LoadAssetAtPath<Material>("Assets/Settings/XRay_Cone.mat");
            Assert.IsNotNull(xray, "premise: no x-ray cone material");
            Assert.AreSame(shader, xray.shader, "XRay_Cone.mat does not use the vision cone shader");
            Assert.AreEqual(1f, xray.GetFloat("_XRay"), 1e-6f, "XRay_Cone.mat is not in its hatched x-ray mode");

            var graphics = AssetDatabase.LoadAssetAtPath<GraphicsSettings>("ProjectSettings/GraphicsSettings.asset");
            Assert.IsNotNull(graphics, "premise: no GraphicsSettings.asset");
            SerializedProperty list = new SerializedObject(graphics).FindProperty("m_AlwaysIncludedShaders");
            bool included = false;
            for (int i = 0; i < list.arraySize; i++)
            {
                included |= list.GetArrayElementAtIndex(i).objectReferenceValue == shader;
            }
            Assert.IsTrue(included, "the vision cone shader is not in Always Included Shaders");
        }
    }
}
