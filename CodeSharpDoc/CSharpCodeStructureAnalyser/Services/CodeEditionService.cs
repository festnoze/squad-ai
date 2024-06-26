using CSharpCodeStructureAnalyser.Models;
using System;

namespace CSharpCodeStructureAnalyser.Services;

public static class CodeEditionService
{
    public static string AddGeneratedSummariesToInitialCode(IEnumerable<StructSummariesInfos> structuresSummariesInfos)
    {
        // Load code from file
        string code = File.ReadAllText(structuresSummariesInfos.First().FilePath);

        // Add methods summaries to the code
        foreach (var structureSummariesInfos in structuresSummariesInfos.OrderByDescending(m => m.IndexShiftCode))
        {
            for (int i = structureSummariesInfos.Methods.Count - 1; i >= 0; i--)
            {
                string methodSummary = "\n" + Indent(structureSummariesInfos.IndentLevel + 1, structureSummariesInfos.Methods[i].GeneratedXmlSummary);
                var index = structureSummariesInfos.IndexShiftCode + structureSummariesInfos.Methods[i].CodeStartIndex;
                code = code.Insert(index, methodSummary);
            }
            // Add global structureSummaries summary to the code
            if (!string.IsNullOrEmpty(structureSummariesInfos.GeneratedSummary))
            {
                string globalSummary = "\n" + Indent(structureSummariesInfos.IndentLevel, structureSummariesInfos.GeneratedSummary);
                code = code.Insert(structureSummariesInfos.IndexShiftCode, globalSummary);
            }
        }
        return code;
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
