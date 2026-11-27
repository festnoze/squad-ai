namespace UnityEngine
{
    public class AudioClip
    {
        public static AudioClip Create(string n, int len, int ch, int rate, bool stream) { return new AudioClip(); }
        public bool SetData(float[] d, int o) { return true; }
    }
    public static class Debug { public static void LogError(object o) { System.Console.WriteLine(o); } public static void Log(object o) { System.Console.WriteLine(o); } }
}
namespace PainterIO.Runtime { public enum BiomeId { Liquid = 0, Fire = 1, Electric = 2 } }
