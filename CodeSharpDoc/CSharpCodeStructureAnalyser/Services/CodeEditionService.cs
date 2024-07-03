using CSharpCodeStructureAnalyser.Models;
using System;
using System.IO;
using System.Reflection;

namespace CSharpCodeStructureAnalyser.Services;

public static class CodeEditionService
{
    public static string AddGeneratedSummariesToInitialCode(IEnumerable<StructSummariesInfos> structuresSummariesInfos)
    {
        // Load code from file
        string code = File.ReadAllText(structuresSummariesInfos.First().FilePath);
        var newCode = code;
        // Add methods summaries to the code
        foreach (var structureSummariesInfos in structuresSummariesInfos.OrderByDescending(m => m.IndexShiftCode))
        {
            for (int i = structureSummariesInfos.Methods.Count - 1; i >= 0; i--)
            {
                var methodSummary = structureSummariesInfos.Methods[i].GeneratedXmlSummary.TrimEnd();
                if (methodSummary.EndsWith("\n"))
                    methodSummary = methodSummary.TrimEnd('\n');
                methodSummary = "\n" + Indent(structureSummariesInfos.IndentLevel + 1, methodSummary);
                var before = newCode.Substring(0, structureSummariesInfos.Methods[i].CodeStartIndex);
                var after = newCode.Substring(structureSummariesInfos.Methods[i].CodeStartIndex);
                newCode = before + methodSummary + after;
            }
            // Add global structureSummaries summary to the code
            if (!string.IsNullOrEmpty(structureSummariesInfos.GeneratedSummary))
            {
                string globalSummary = "\n" + Indent(structureSummariesInfos.IndentLevel, structureSummariesInfos.GeneratedSummary.TrimEnd());
                var before = newCode.Substring(0, structureSummariesInfos.IndexShiftCode);
                var after = newCode.Substring(structureSummariesInfos.IndexShiftCode);
                newCode = before + globalSummary + after;
            }
        }
        return newCode;
    }

    public static void AddGeneratedSummariesToCodeFilesAndSave(IEnumerable<StructSummariesInfos> structuresSummaries)
    {
        var groupedByFilePath = structuresSummaries.GroupBy(s => s.FilePath);
        // Display the grouped result
        foreach (var group in groupedByFilePath)
        {
            var code = AddGeneratedSummariesToInitialCode(group.ToList());
            File.WriteAllText(group.First().FilePath, code);
        }
    }

    private static string Indent(int level, string text)
    {
        var indent = new string(' ', level * 4); // Assuming 4 spaces per indent level
        var indentedText = text.Split('\n').Select(line => indent + line).ToArray();
        return string.Join("\n", indentedText);
    }
}
