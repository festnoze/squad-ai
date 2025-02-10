namespace CSharpCodeStructureAnalyser.Models;

using System.Collections.Generic;
using System.Text.Json.Serialization;

public class MethodSummaryInfo
{
    [JsonPropertyName("code_start_index")]
    public int CodeStartIndex { get; set; }

    [JsonPropertyName("summary")]
    public string Summary { get; set; }

    public MethodSummaryInfo(int codeStartIndex, string summary = "")
    {
        CodeStartIndex = codeStartIndex;
        Summary = summary ?? "";
    }
}

public class StructSummariesInfos
{
    [JsonPropertyName("file_path")]
    public string FilePath { get; set; }

    [JsonPropertyName("index_shift_code")]
    public int IndexShiftCode { get; set; }

    [JsonPropertyName("indent_level")]
    public int IndentLevel { get; set; }

    [JsonPropertyName("summary")]
    public string Summary { get; set; }

    [JsonPropertyName("methods")]
    public List<MethodSummaryInfo> Methods { get; set; }

    public StructSummariesInfos(string filePath, int indexShiftCode, int indentLevel, string summary, List<MethodSummaryInfo>? methods = null)
    {
        FilePath = filePath;
        IndexShiftCode = indexShiftCode;
        IndentLevel = indentLevel;
        Summary = summary;
        Methods = methods ?? new List<MethodSummaryInfo>();
    }
}
