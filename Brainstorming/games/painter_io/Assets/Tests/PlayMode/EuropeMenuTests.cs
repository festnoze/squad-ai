using System.Collections;
using NUnit.Framework;
using PainterIO.Core;
using PainterIO.Runtime;
using UnityEngine;
using UnityEngine.TestTools;

public sealed class EuropeMenuTests
{
    private const string TestKey = "pio.europe.progress.playmode-test";

    [UnityTest]
    public IEnumerator OpensMapAndStartsACountryRound()
    {
        if (GameDirector.Instance != null)
        {
            Object.Destroy(GameDirector.Instance.gameObject);
            yield return null;
        }
        EuropeProgress.StorageKey = TestKey;
        EuropeProgress.ResetProgress();
        SaveData.MemoryOnly = true;   // the results below record stats: never into the player's PlayerPrefs
        SaveData.ResetTestSettings();
        var root = new GameObject("Europe menu test");
        try
        {
            var director = root.AddComponent<GameDirector>();
            Assert.That(director.State, Is.EqualTo(GameState.Menu));
            var ui = UiRoot.Instance;

            // Rule v1.7 (countries first): no "Pays" button; JOUER opens the country screen.
            var menuButtons = ui.Menu.Canvas.GetComponentsInChildren<UnityEngine.UI.Button>(true);
            Assert.That(System.Array.Exists(menuButtons, b => b.name == "Countries"), Is.False, "the Pays button is gone");
            var play = System.Array.Find(menuButtons, b => b.name == "Face" && b.transform.parent.name == "Play");
            Assert.That(play, Is.Not.Null);
            play.onClick.Invoke();
            yield return null;
            yield return null;
            Assert.That(director.State, Is.EqualTo(GameState.Menu), "JOUER does not start a square round");
            Assert.That(EuropeScreen.Active, Is.Not.Null);
            Assert.That(EuropeScreen.Active.Visible, Is.True, "JOUER shows the country screen");
            Assert.That(ui.Menu.Visible, Is.False);

            var map = root.GetComponentInChildren<EuropeMapView>();
            Assert.That(map, Is.Not.Null);
            var screen = EuropeScreen.Active;
            Assert.That(screen, Is.Not.Null);
            Assert.That(map.Display, Is.Not.Null);
            if (SystemInfo.graphicsDeviceType != UnityEngine.Rendering.GraphicsDeviceType.Null)
            {
                Assert.That(map.Display.IsCreated(), Is.True);
                Assert.That(MapHasLand(map.Display), Is.True, "The map camera must render land over the sea.");
            }

            // A new campaign: France selected, its flag the only one standing.
            Assert.That(screen.SelectedCode, Is.EqualTo("FR"));
            Assert.That(map.ActiveFlagCount, Is.EqualTo(1));
            Assert.That(map.HasFlag(screen.IndexOf("FR")), Is.True);
            Assert.That(map.ActiveMedalCount, Is.EqualTo(0));
            var cloth = map.transform.Find("Flags/Flag FR/Cloth").GetComponent<Renderer>();
            Assert.That(cloth.enabled && cloth.gameObject.activeInHierarchy, Is.True);

            // The arrows skip locked countries: France is the only stop.
            screen.StepSelection(1);
            Assert.That(screen.SelectedCode, Is.EqualTo("FR"));

            // A locked country can be looked at but not played.
            Assert.That(screen.SelectCode("DE"), Is.True);
            Assert.That(screen.PlaySelected(), Is.False);
            Assert.That(director.State, Is.EqualTo(GameState.Menu));

            // A first win on France: two flags rise next time the map opens, France shows its medal.
            AssertCount(EuropeProgress.RecordWin("FR"), 2);
            ui.CloseEurope();
            yield return null;
            ui.OpenEurope();
            yield return null;
            Assert.That(map.ActiveFlagCount, Is.EqualTo(2));
            Assert.That(map.ActiveMedalCount, Is.EqualTo(1));
            Assert.That(map.IsRevealing, Is.True);
            Assert.That(EuropeProgress.Current.PendingReveal.Count, Is.EqualTo(0), "the reveal plays once");
            Assert.That(EuropeProgress.Current.StateOf(screen.SelectedCode), Is.EqualTo(CountryProgress.Unlocked));

            // Hidden reset: five taps on the title show the button, which asks for a confirmation.
            var buttons = screen.Canvas.GetComponentsInChildren<UnityEngine.UI.Button>(true);
            var titleTaps = System.Array.Find(buttons, b => b.name == "Heading taps");
            var reset = System.Array.Find(buttons, b => b.name == "Reset progress");
            Assert.That(reset.gameObject.activeSelf, Is.False);
            for (int i = 0; i < EuropeScreen.TitleTapsToReveal; i++) titleTaps.onClick.Invoke();
            Assert.That(reset.gameObject.activeSelf, Is.True);
            reset.onClick.Invoke();
            Assert.That(EuropeProgress.Current.WonCount, Is.EqualTo(1), "the first tap only arms the reset");
            reset.onClick.Invoke();
            Assert.That(EuropeProgress.Current.WonCount, Is.EqualTo(0));
            Assert.That(EuropeProgress.Current.PlayablePool(), Is.EqualTo(new[] { "FR" }));
            Assert.That(map.ActiveFlagCount, Is.EqualTo(1));
            Assert.That(map.ActiveMedalCount, Is.EqualTo(0));
            Assert.That(reset.gameObject.activeSelf, Is.False);

            Assert.That(screen.SelectCode("FR"), Is.True);
            Assert.That(screen.PlaySelected(), Is.True);
            Assert.That(director.State, Is.EqualTo(GameState.Playing));
            Assert.That(director.Session.Sim.Arena.Polygon, Is.Not.Null);
            Assert.That(director.Session.Sim.Config.RoundDuration, Is.EqualTo(900.0), "rule v1.7: 15 min country rounds");
            Assert.That(director.Session.Sim.Config.ConquestShare, Is.EqualTo(1.0), "the goal is 100 %");
            Assert.That(director.Session.Sim.ConquestCellCount, Is.GreaterThan(0));
            Assert.That(map.gameObject.activeSelf, Is.False);

            // Results: REJOUER replays the same country, PAYS SUIVANT goes on to the country screen.
            director.ShowResults();
            Assert.That(director.State, Is.EqualTo(GameState.Results));
            yield return new WaitForSecondsRealtime(ResultsScreen.InputGuardSeconds + 0.15f);
            var resultButtons = ui.Results.Canvas.GetComponentsInChildren<UnityEngine.UI.Button>(true);
            var replay = System.Array.Find(resultButtons, b => b.name == "Replay");
            var next = System.Array.Find(resultButtons, b => b.name == "Face" && b.transform.parent.name == "NextCountry");
            Assert.That(replay, Is.Not.Null);
            Assert.That(next, Is.Not.Null);
            replay.onClick.Invoke();
            Assert.That(director.State, Is.EqualTo(GameState.Playing));
            Assert.That(director.Session.Sim.Arena.Polygon, Is.Not.Null, "REJOUER keeps the country");
            Assert.That(director.SelectedCountry.code, Is.EqualTo("FR"));

            director.ShowResults();
            yield return new WaitForSecondsRealtime(ResultsScreen.InputGuardSeconds + 0.15f);
            next.onClick.Invoke();
            yield return null;
            Assert.That(director.State, Is.EqualTo(GameState.Menu));
            Assert.That(EuropeScreen.Active.Visible, Is.True, "PAYS SUIVANT shows the country screen");
            Assert.That(ui.Menu.Visible, Is.False);
            Assert.That(map.gameObject.activeSelf, Is.True);
            Assert.That(director.Session.IsAttract, Is.True, "the attract match runs behind the country screen");

            // Back from the country screen: the menu (whose JOUER brings the countries again).
            ui.CloseEurope();
            yield return null;
            Assert.That(ui.Menu.Visible, Is.True);
            director.StartRound();   // launch flags, probe and tests may still play; the menu never does it with no country
            Assert.That(director.Session.Sim.Arena.Polygon, Is.Not.Null, "the last country is kept");
            director.ToMenu();
            Assert.That(director.Session.Sim.Arena.Polygon, Is.Null);
        }
        finally
        {
            Object.Destroy(root);
            EuropeProgress.ResetProgress();
            PlayerPrefs.DeleteKey(TestKey);
            EuropeProgress.StorageKey = null;
            SaveData.MemoryOnly = false;
        }
        yield return null;
    }

    private static void AssertCount(System.Collections.Generic.IReadOnlyList<string> list, int count)
    {
        Assert.That(list.Count, Is.EqualTo(count));
    }

    private static bool MapHasLand(RenderTexture map)
    {
        RenderTexture previous = RenderTexture.active;
        var pixels = new Texture2D(map.width, map.height, TextureFormat.RGB24, false);
        try
        {
            RenderTexture.active = map;
            pixels.ReadPixels(new Rect(0, 0, map.width, map.height), 0, 0);
            Color32[] colors = pixels.GetPixels32();
            return System.Array.Exists(colors, color => color.g > 80 && color.b > 80);
        }
        finally
        {
            RenderTexture.active = previous;
            Object.Destroy(pixels);
        }
    }
}
