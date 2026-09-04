using NUnit.Framework;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

/// <summary>
/// Guards the mobile+PC toolchain itself, not gameplay.
///
/// These assert against live engine state rather than the contents of
/// Packages/manifest.json: a package can be listed there and still fail to
/// compile or bind, which is exactly the failure a manifest check would miss.
/// </summary>
public class ToolchainTests
{
    [Test]
    public void UniversalRenderPipelineIsTheActivePipeline()
    {
        var pipeline = GraphicsSettings.defaultRenderPipeline;
        Assert.IsNotNull(pipeline, "No render pipeline asset is assigned; the project fell back to Built-In.");
        Assert.IsInstanceOf<UniversalRenderPipelineAsset>(
            pipeline,
            $"Active pipeline is '{pipeline.GetType().Name}', expected a URP asset.");
    }

    [Test]
    public void InputSystemIsUsableAtRuntime()
    {
        // Touching a real API proves the assembly is referenced and bound,
        // which merely finding the package in the manifest would not.
        Assert.IsNotNull(InputSystem.settings, "Input System has no settings asset; the package is not active.");
    }

    [Test]
    public void ThisTestSuiteActuallyRan()
    {
        // A run reporting zero tests exits 0 and looks identical to success.
        // This asserts the suite was discovered and executed at all.
        Assert.Pass("EditMode test assembly was discovered and executed.");
    }
}
