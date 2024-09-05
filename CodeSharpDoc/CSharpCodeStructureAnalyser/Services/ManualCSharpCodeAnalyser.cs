namespace CSharpCodeStructureAnalyser.Services;

using CSharpCodeStructureAnalyser.Models;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;

public class ManualCSharpCodeAnalyser
{
    private static readonly string[] StructureSeparatorsArray = new[]
    {
        "public class ", "protected class ", "private class ", "internal class ",
        "public static class ", "protected static class ", "private static class ", "internal static class ",
        "public interface ", "protected interface ", "private interface ", "internal interface",
        "public enum ", "protected enum ", "private enum ", "internal enum "
    };

    private static readonly string[] MethodSeparators = new[]
    {
        "public ", "protected ", "private ", "internal "
    };

    private static readonly Regex StructurePattern = new Regex(string.Join("|", StructureSeparatorsArray.Select(Regex.Escape)));
    private static readonly Regex MethodPattern = new Regex(string.Join("|", MethodSeparators.Select(Regex.Escape)));

    public static List<StructureMethodInfo> ExtractMethodsFromCodeFile(string code)
    {
        var allParsedStructures = new List<StructureMethodInfo>();
        var structures = GetStructuresFromCodeFile(code);

        if (structures != null && structures.Count > 0)
        {
            allParsedStructures.AddRange(structures);
        }
        return allParsedStructures;
    }

    private static List<StructureMethodInfo> GetStructuresFromCodeFile(string code)
    {
        var foundStructSeparators = StructurePattern.Matches(code).Cast<Match>().Select(m => m.Value).ToList();
        var separatorIndexes = StructurePattern.Matches(code).Cast<Match>().Select(m => m.Index + m.Length).ToList();
        var splittedContents = StructurePattern.Split(code).ToList();

        if (foundStructSeparators.Count == 0 || splittedContents.Count < 2)
        {
            return new List<StructureMethodInfo>();
        }

        var structures = new List<StructureMethodInfo>();
        for (int i = 0; i < foundStructSeparators.Count; i++)
        {
            var structType = foundStructSeparators[i].Trim().Split().Last();
            if (structType == "class" || structType == "interface")
            {
                var structName = splittedContents[i+1].Substring(0, splittedContents[i+1].IndexOf(" ")).Trim();
                var methods = ExtractMethods(structType, splittedContents[i + 1], separatorIndexes[i]);
                structures.Add(new StructureMethodInfo(
                                    structName,
                                    structType,
                                    methods));
            }
        }

        return structures;
    }

    private static List<MethodInfo> ExtractMethods(string structureType, string code, int indexShiftCode)
    {
        var matches = MethodPattern.Matches(code).Cast<Match>().ToList();
        var methods = new List<MethodInfo>();

        foreach (var match in matches)
        {
            var signature = code.Substring(match.Index, code.IndexOf("\n", match.Index) - match.Index).Trim();
            if (!IsProperty(structureType, signature))
            {
                var methodName = signature.Split("(").First().Split().Last();
                methods.Add(new MethodInfo(
                                methodName,
                                match.Index + indexShiftCode));
            }
        }

        return methods;
    }

    private static bool IsProperty(string structType, string firstLine)
    {
        if (structType == "class")
        {
            return firstLine.EndsWith(";") || firstLine.EndsWith("; }") || firstLine.EndsWith(";");
        }
        else if (structType == "interface")
        {
            return !firstLine.Contains("(") && !firstLine.Contains(")");
        }
        return false;
    }

    public record StructureMethodInfo
    {
        public StructureMethodInfo(string structureName, string structureType, List<MethodInfo> methods)
        {
            StructureName = structureName;
            StructureType = structureType;
            Methods = methods;
        }

        public string StructureName { get; set; }
        public string StructureType { get; set; }
        public List<MethodInfo> Methods { get; set; }
    }

    public record MethodInfo
    {
        public MethodInfo(string methodName, int startIndex)
        {
            MethodName = methodName;
            StartIndex = startIndex;
        }

        public string MethodName { get; set; }
        public int StartIndex { get; set; }
    }
}

