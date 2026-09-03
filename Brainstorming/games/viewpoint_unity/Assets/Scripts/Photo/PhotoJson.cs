using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace Viewpoint
{
    /// <summary>
    /// Raised when the shipped data does not match the schema of PRD sections 6.1
    /// and 13.1. The data is a contract: a bad shape is a load error, never a
    /// silent default that would only be noticed as a wrong puzzle at play time.
    /// </summary>
    public sealed class PhotoDataException : Exception
    {
        public PhotoDataException(string message) : base(message) { }
    }

    /// <summary>
    /// Reads a JSON [x, y, z] array as a Vector3. The values stay in DESIGN space
    /// (PRD 4.1): the z mirror belongs to DesignSpace.ToUnity, at the point where
    /// a world or local position is set, and nowhere else.
    /// </summary>
    public sealed class Vector3ArrayConverter : JsonConverter
    {
        public override bool CanConvert(Type objectType)
        {
            return objectType == typeof(Vector3);
        }

        public override object ReadJson(JsonReader reader, Type objectType, object existingValue, JsonSerializer serializer)
        {
            JToken token = JToken.Load(reader);
            if (token.Type != JTokenType.Array)
            {
                throw new JsonSerializationException("a vector must be a [x, y, z] array");
            }
            JArray array = (JArray)token;
            if (array.Count != 3)
            {
                throw new JsonSerializationException("a vector must hold exactly 3 numbers, got " + array.Count);
            }
            return new Vector3(Component(array[0]), Component(array[1]), Component(array[2]));
        }

        public override void WriteJson(JsonWriter writer, object value, JsonSerializer serializer)
        {
            Vector3 v = (Vector3)value;
            writer.WriteStartArray();
            writer.WriteValue(v.x);
            writer.WriteValue(v.y);
            writer.WriteValue(v.z);
            writer.WriteEndArray();
        }

        static float Component(JToken token)
        {
            if (token.Type != JTokenType.Integer && token.Type != JTokenType.Float)
            {
                throw new JsonSerializationException("a vector component must be a number");
            }
            return (float)token;
        }
    }

    /// <summary>
    /// Loads the two data files of PRD 15.5 into the plain models of Models.cs.
    /// Pure C# with no MonoBehaviour and no scene, so an EditMode test can call it.
    /// Values stay in design space; nothing here converts to Unity space.
    /// </summary>
    public static class PhotoJson
    {
        /// Resources paths carry no extension (Resources.Load strips it).
        public const string PhotosResource = "Data/photos";
        public const string LevelsResource = "Data/levels";

        /// Prop kinds the expander of PRD 6.2 knows. Anything else is a load error.
        static readonly string[] KnownPropKinds =
        {
            "box", "cylinder", "battery", "bridge", "stairs", "arch", "photo"
        };

        static readonly JsonSerializer VectorSerializer = MakeVectorSerializer();

        static JsonSerializer MakeVectorSerializer()
        {
            JsonSerializer serializer = new JsonSerializer();
            serializer.Converters.Add(new Vector3ArrayConverter());
            return serializer;
        }

        // -------------------------------------------------------------- photos

        /// <summary>Reads Resources/Data/photos.json, keyed by photo id.</summary>
        public static Dictionary<string, PhotoDef> LoadPhotos()
        {
            JObject root = LoadRoot(PhotosResource);
            JObject photos = AsObject(Require(root, "photos", "photos.json"), "photos");

            Dictionary<string, PhotoDef> result = new Dictionary<string, PhotoDef>();
            foreach (JProperty property in photos.Properties())
            {
                string id = property.Name;
                string where = "photo '" + id + "'";
                result[id] = ReadPhoto(AsObject(property.Value, where), where);
            }

            // A photo-in-photo prop must name a photo of this same catalog: a
            // dangling id would only show up as an empty pickup after a placement.
            foreach (KeyValuePair<string, PhotoDef> entry in result)
            {
                List<PhotoProp> props = entry.Value.Props;
                for (int i = 0; i < props.Count; i++)
                {
                    PhotoProp prop = props[i];
                    if (prop.Kind == "photo" && !result.ContainsKey(prop.Id))
                    {
                        throw Fail("photo '" + entry.Key + "' nests unknown photo id '" + prop.Id + "'");
                    }
                }
            }
            return result;
        }

        static PhotoDef ReadPhoto(JObject source, string where)
        {
            PhotoDef def = new PhotoDef();
            def.Title = ReadString(source, "title", where);
            def.Hint = ReadString(source, "hint", where);
            def.Seal = ReadStringOr(source, "seal", null, where);
            // PRD 6.1: erase_depth defaults to 12 when absent.
            def.EraseDepth = ReadFloatOr(source, "erase_depth", PhotoMath.DefaultEraseDepth, where);
            if (def.EraseDepth <= 0f)
            {
                throw Fail(where + ": erase_depth must be positive");
            }

            def.Props = new List<PhotoProp>();
            JArray props = AsArray(Require(source, "props", where), where + " props");
            for (int i = 0; i < props.Count; i++)
            {
                string propWhere = where + " prop " + i;
                def.Props.Add(ReadProp(AsObject(props[i], propWhere), propWhere));
            }

            def.Backdrop = ReadBackdrop(Field(source, "backdrop"), where);
            return def;
        }

        static PhotoProp ReadProp(JObject source, string where)
        {
            PhotoProp prop = new PhotoProp();
            prop.Kind = ReadString(source, "kind", where);
            if (!IsKnownPropKind(prop.Kind))
            {
                throw Fail(where + ": unknown prop kind '" + prop.Kind + "'");
            }
            prop.Pos = ReadVector(source, "pos", where);
            // The original defaults a missing size to zero and a missing color to
            // stone (photo_defs.gd expand_prop); the shipped data always states both.
            prop.Size = ReadVectorOr(source, "size", Vector3.zero, where);
            prop.Color = ReadColorKey(source, "color", "stone", where);
            prop.Loose = ReadBoolOr(source, "loose", false, where);
            prop.Id = ReadStringOr(source, "id", null, where);
            if (prop.Kind == "photo" && string.IsNullOrEmpty(prop.Id))
            {
                throw Fail(where + ": a 'photo' prop must name the nested photo with 'id'");
            }
            return prop;
        }

        /// <summary>
        /// A photo either has a painted backdrop or none at all. The door writes an
        /// empty object ("backdrop": {}) rather than omitting the key, so an empty
        /// object means no backdrop, exactly like a missing key.
        /// </summary>
        static PhotoBackdrop ReadBackdrop(JToken token, string where)
        {
            if (token == null)
            {
                return null;
            }
            JObject source = AsObject(token, where + " backdrop");
            if (!source.HasValues)
            {
                return null;
            }
            PhotoBackdrop backdrop = new PhotoBackdrop();
            backdrop.Depth = ReadFloat(source, "depth", where + " backdrop");
            backdrop.Top = ReadColorKey(source, "top", null, where + " backdrop");
            backdrop.Bottom = ReadColorKey(source, "bottom", null, where + " backdrop");
            if (backdrop.Depth <= 0f)
            {
                throw Fail(where + " backdrop: depth must be positive");
            }
            return backdrop;
        }

        static bool IsKnownPropKind(string kind)
        {
            for (int i = 0; i < KnownPropKinds.Length; i++)
            {
                if (KnownPropKinds[i] == kind)
                {
                    return true;
                }
            }
            return false;
        }

        // -------------------------------------------------------------- levels

        /// <summary>Reads Resources/Data/levels.json: the 25 levels and the decor islands.</summary>
        public static (List<LevelDef> levels, List<IslandDef> islands) LoadLevels()
        {
            JObject root = LoadRoot(LevelsResource);

            List<IslandDef> islands = new List<IslandDef>();
            JArray islandArray = AsArrayOrNull(Field(root, "decor_islands"), "decor_islands");
            if (islandArray != null)
            {
                for (int i = 0; i < islandArray.Count; i++)
                {
                    string where = "decor island " + i;
                    JObject source = AsObject(islandArray[i], where);
                    IslandDef island = new IslandDef();
                    island.Pos = ReadVector(source, "pos", where);
                    island.Size = ReadVector(source, "size", where);
                    islands.Add(island);
                }
            }

            List<LevelDef> levels = new List<LevelDef>();
            JArray levelArray = AsArray(Require(root, "levels", "levels.json"), "levels");
            for (int i = 0; i < levelArray.Count; i++)
            {
                // Levels are named by their human number (1 based) in error messages.
                string where = "level " + (i + 1);
                levels.Add(ReadLevel(AsObject(levelArray[i], where), where));
            }
            return (levels, islands);
        }

        static LevelDef ReadLevel(JObject source, string where)
        {
            LevelDef def = new LevelDef();
            def.Name = ReadString(source, "name", where);
            def.Subtitle = ReadString(source, "subtitle", where);
            def.Spawn = ReadVector(source, "spawn", where);
            def.SpawnYaw = ReadFloat(source, "spawn_yaw", where);
            def.KillY = ReadFloat(source, "kill_y", where);

            def.Platforms = new List<PlatformDef>();
            JArray platforms = AsArrayOrNull(Field(source, "platforms"), where + " platforms");
            if (platforms != null)
            {
                for (int i = 0; i < platforms.Count; i++)
                {
                    string itemWhere = where + " platform " + i;
                    JObject item = AsObject(platforms[i], itemWhere);
                    PlatformDef platform = new PlatformDef();
                    platform.Pos = ReadVector(item, "pos", itemWhere);
                    platform.Size = ReadVector(item, "size", itemWhere);
                    platform.Soft = ReadBoolOr(item, "soft", false, itemWhere);
                    def.Platforms.Add(platform);
                }
            }

            def.Decor = new List<DecorDef>();
            JArray decor = AsArrayOrNull(Field(source, "decor"), where + " decor");
            if (decor != null)
            {
                for (int i = 0; i < decor.Count; i++)
                {
                    string itemWhere = where + " decor " + i;
                    JObject item = AsObject(decor[i], itemWhere);
                    DecorDef marker = new DecorDef();
                    marker.Pos = ReadVector(item, "pos", itemWhere);
                    marker.Size = ReadVector(item, "size", itemWhere);
                    // level_builder.gd defaults a marker with no color to wood.
                    marker.Color = ReadColorKey(item, "color", "wood", itemWhere);
                    marker.Photo = ReadStringOr(item, "photo", null, itemWhere);
                    Vector3 aim;
                    marker.HasAim = TryReadVector(item, "aim", itemWhere, out aim);
                    marker.Aim = aim;
                    marker.Roll = ReadIntOr(item, "roll", 0, itemWhere);
                    def.Decor.Add(marker);
                }
            }

            def.Erasables = new List<ErasableDef>();
            JArray erasables = AsArrayOrNull(Field(source, "erasables"), where + " erasables");
            if (erasables != null)
            {
                for (int i = 0; i < erasables.Count; i++)
                {
                    string itemWhere = where + " erasable " + i;
                    JObject item = AsObject(erasables[i], itemWhere);
                    ErasableDef erasable = new ErasableDef();
                    erasable.Pos = ReadVector(item, "pos", itemWhere);
                    erasable.Size = ReadVector(item, "size", itemWhere);
                    def.Erasables.Add(erasable);
                }
            }

            def.Cages = new List<CageDef>();
            JArray cages = AsArrayOrNull(Field(source, "cages"), where + " cages");
            if (cages != null)
            {
                for (int i = 0; i < cages.Count; i++)
                {
                    string itemWhere = where + " cage " + i;
                    JObject item = AsObject(cages[i], itemWhere);
                    CageDef cage = new CageDef();
                    cage.Pos = ReadVector(item, "pos", itemWhere);
                    cage.Size = ReadVector(item, "size", itemWhere);
                    cage.Sealed = ReadBoolOr(item, "sealed", false, itemWhere);
                    cage.Roof = ReadBoolOr(item, "roof", true, itemWhere);
                    // level_builder.gd: erasable defaults to true, and steel always
                    // wins over lavender. Resolved here so the two flags can never
                    // contradict each other downstream.
                    cage.Erasable = ReadBoolOr(item, "erasable", true, itemWhere) && !cage.Sealed;
                    def.Cages.Add(cage);
                }
            }

            def.Photos = new List<PhotoPlacementDef>();
            JArray photos = AsArrayOrNull(Field(source, "photos"), where + " photos");
            if (photos != null)
            {
                for (int i = 0; i < photos.Count; i++)
                {
                    string itemWhere = where + " photo " + i;
                    JObject item = AsObject(photos[i], itemWhere);
                    PhotoPlacementDef placement = new PhotoPlacementDef();
                    placement.Id = ReadString(item, "id", itemWhere);
                    placement.Pos = ReadVector(item, "pos", itemWhere);
                    def.Photos.Add(placement);
                }
            }

            def.Batteries = ReadVectorList(source, "batteries", where);
            def.SealedBatteries = ReadVectorList(source, "sealed_batteries", where);

            JToken cameraToken = Field(source, "camera");
            if (cameraToken != null)
            {
                string itemWhere = where + " camera";
                JObject item = AsObject(cameraToken, itemWhere);
                CameraDef camera = new CameraDef();
                camera.Pos = ReadVector(item, "pos", itemWhere);
                camera.Films = ReadInt(item, "films", itemWhere);
                def.Camera = camera;
            }

            string teleWhere = where + " teleporter";
            JObject teleSource = AsObject(Require(source, "teleporter", where), teleWhere);
            TeleporterDef teleporter = new TeleporterDef();
            teleporter.Pos = ReadVector(teleSource, "pos", teleWhere);
            teleporter.Required = ReadInt(teleSource, "required", teleWhere);
            def.Teleporter = teleporter;

            return def;
        }

        static List<Vector3> ReadVectorList(JObject source, string key, string where)
        {
            List<Vector3> result = new List<Vector3>();
            JArray array = AsArrayOrNull(Field(source, key), where + " " + key);
            if (array == null)
            {
                return result;
            }
            for (int i = 0; i < array.Count; i++)
            {
                result.Add(ToVector(array[i], where + " " + key + " " + i));
            }
            return result;
        }

        // ------------------------------------------------------------- reading

        static JObject LoadRoot(string resource)
        {
            TextAsset asset = Resources.Load<TextAsset>(resource);
            if (asset == null)
            {
                throw Fail("Resources/" + resource + ".json is missing");
            }
            try
            {
                return JObject.Parse(asset.text);
            }
            catch (JsonException error)
            {
                throw Fail("Resources/" + resource + ".json is not valid JSON: " + error.Message);
            }
        }

        /// <summary>The value of a key, or null when it is absent or JSON null.</summary>
        static JToken Field(JObject source, string key)
        {
            JToken token = source[key];
            if (token == null || token.Type == JTokenType.Null)
            {
                return null;
            }
            return token;
        }

        static JToken Require(JObject source, string key, string where)
        {
            JToken token = Field(source, key);
            if (token == null)
            {
                throw Fail(where + ": missing required field '" + key + "'");
            }
            return token;
        }

        static JObject AsObject(JToken token, string where)
        {
            JObject value = token as JObject;
            if (value == null)
            {
                throw Fail(where + ": expected an object");
            }
            return value;
        }

        static JArray AsArray(JToken token, string where)
        {
            JArray value = token as JArray;
            if (value == null)
            {
                throw Fail(where + ": expected an array");
            }
            return value;
        }

        static JArray AsArrayOrNull(JToken token, string where)
        {
            if (token == null)
            {
                return null;
            }
            return AsArray(token, where);
        }

        static string ReadString(JObject source, string key, string where)
        {
            JToken token = Require(source, key, where);
            if (token.Type != JTokenType.String)
            {
                throw Fail(where + ": field '" + key + "' must be a string");
            }
            return (string)token;
        }

        static string ReadStringOr(JObject source, string key, string fallback, string where)
        {
            JToken token = Field(source, key);
            if (token == null)
            {
                return fallback;
            }
            if (token.Type != JTokenType.String)
            {
                throw Fail(where + ": field '" + key + "' must be a string");
            }
            return (string)token;
        }

        /// <summary>A palette key, checked against Palette so a typo dies at load.</summary>
        static string ReadColorKey(JObject source, string key, string fallback, string where)
        {
            string value = ReadStringOr(source, key, fallback, where);
            if (value == null)
            {
                throw Fail(where + ": missing required field '" + key + "'");
            }
            if (!Palette.Has(value))
            {
                throw Fail(where + ": unknown palette color '" + value + "' for '" + key + "'");
            }
            return value;
        }

        static float ReadFloat(JObject source, string key, string where)
        {
            JToken token = Require(source, key, where);
            if (token.Type != JTokenType.Integer && token.Type != JTokenType.Float)
            {
                throw Fail(where + ": field '" + key + "' must be a number");
            }
            return (float)token;
        }

        static float ReadFloatOr(JObject source, string key, float fallback, string where)
        {
            if (Field(source, key) == null)
            {
                return fallback;
            }
            return ReadFloat(source, key, where);
        }

        static int ReadInt(JObject source, string key, string where)
        {
            JToken token = Require(source, key, where);
            if (token.Type != JTokenType.Integer)
            {
                throw Fail(where + ": field '" + key + "' must be a whole number");
            }
            return (int)token;
        }

        static int ReadIntOr(JObject source, string key, int fallback, string where)
        {
            if (Field(source, key) == null)
            {
                return fallback;
            }
            return ReadInt(source, key, where);
        }

        static bool ReadBoolOr(JObject source, string key, bool fallback, string where)
        {
            JToken token = Field(source, key);
            if (token == null)
            {
                return fallback;
            }
            if (token.Type != JTokenType.Boolean)
            {
                throw Fail(where + ": field '" + key + "' must be true or false");
            }
            return (bool)token;
        }

        static Vector3 ReadVector(JObject source, string key, string where)
        {
            return ToVector(Require(source, key, where), where + " '" + key + "'");
        }

        static Vector3 ReadVectorOr(JObject source, string key, Vector3 fallback, string where)
        {
            JToken token = Field(source, key);
            if (token == null)
            {
                return fallback;
            }
            return ToVector(token, where + " '" + key + "'");
        }

        static bool TryReadVector(JObject source, string key, string where, out Vector3 value)
        {
            JToken token = Field(source, key);
            if (token == null)
            {
                value = Vector3.zero;
                return false;
            }
            value = ToVector(token, where + " '" + key + "'");
            return true;
        }

        static Vector3 ToVector(JToken token, string where)
        {
            try
            {
                return token.ToObject<Vector3>(VectorSerializer);
            }
            catch (JsonException error)
            {
                throw Fail(where + ": " + error.Message);
            }
        }

        static PhotoDataException Fail(string message)
        {
            Debug.LogError("Viewpoint data: " + message);
            return new PhotoDataException(message);
        }
    }
}
