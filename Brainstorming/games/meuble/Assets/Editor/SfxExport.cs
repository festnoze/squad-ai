using System.IO;
using System.Reflection;
using UnityEngine;

namespace OutOfSight.Editor
{
    /// <summary>
    /// Writes every sound the game synthesizes in code (Sfx's AudioClip properties) to Build/sounds/*.wav, so they can be
    /// listened to like the recorded assets. Batch: -executeMethod OutOfSight.Editor.SfxExport.Run
    /// </summary>
    public static class SfxExport
    {
        public static void Run()
        {
            string dir = Path.GetFullPath("Build/sounds");
            Directory.CreateDirectory(dir);
            var go = new GameObject("SfxExport");
            try
            {
                var sfx = go.AddComponent<OutOfSight.Sfx>();
                sfx.Init();
                int written = 0;
                foreach (PropertyInfo p in typeof(OutOfSight.Sfx).GetProperties(BindingFlags.Public | BindingFlags.Instance))
                {
                    if (p.PropertyType != typeof(AudioClip) || p.Name.StartsWith("Last"))
                    {
                        continue;
                    }
                    var clip = p.GetValue(sfx) as AudioClip;
                    if (clip == null)
                    {
                        continue;
                    }
                    WriteWav(Path.Combine(dir, p.Name + ".wav"), clip);
                    written++;
                }
                Debug.Log($"[SfxExport] {written} synthesized clips written to {dir}");
            }
            finally
            {
                Object.DestroyImmediate(go);
            }
        }

        private static void WriteWav(string path, AudioClip clip)
        {
            var data = new float[clip.samples * clip.channels];
            clip.GetData(data, 0);
            using var w = new BinaryWriter(File.Create(path));
            int bytes = data.Length * 2;
            w.Write(System.Text.Encoding.ASCII.GetBytes("RIFF"));
            w.Write(36 + bytes);
            w.Write(System.Text.Encoding.ASCII.GetBytes("WAVEfmt "));
            w.Write(16);
            w.Write((short)1);
            w.Write((short)clip.channels);
            w.Write(clip.frequency);
            w.Write(clip.frequency * clip.channels * 2);
            w.Write((short)(clip.channels * 2));
            w.Write((short)16);
            w.Write(System.Text.Encoding.ASCII.GetBytes("data"));
            w.Write(bytes);
            foreach (float s in data)
            {
                w.Write((short)(Mathf.Clamp(s, -1f, 1f) * short.MaxValue));
            }
        }
    }
}
