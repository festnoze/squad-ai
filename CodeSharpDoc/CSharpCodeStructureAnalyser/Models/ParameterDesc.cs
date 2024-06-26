using Newtonsoft.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace CSharpCodeStructureAnalyser.Models;

public record ParameterDesc : BaseDesc
{
    [JsonPropertyName("param_name")]
    public string ParamName { get; set; }

    [JsonPropertyName("param_type")]
    public string ParamType { get; set; }

    [JsonPropertyName("has_default_value")]
    public bool HasDefaultValue { get; set; }

    [JsonPropertyName("default_value")]
    public string? DefaultValue { get; set; }

    [JsonPropertyName("description")]
    public string? Description { get; set; }

    [JsonPropertyName("extra_infos")]
    public string? ExtraInfos { get; set; }

    public ParameterDesc(string paramName, string paramType, bool hasDefaultValue = false, string? defaultValue = null, string? description = null, string? extraInfos = null)
        : base(paramName)
    {
        ParamName = paramName;
        ParamType = paramType;
        HasDefaultValue = hasDefaultValue;
        DefaultValue = defaultValue;
        Description = description;
        ExtraInfos = extraInfos;
    }

    public static Tuple<List<string>, string, string, string> ParseParameterSignature(string param)
    {
        var pattern = new Regex(
            @"(?:\[(.*?)\]\s*)?" + // Match attributes, if any
            @"(?<type>\w+(\<.*?\>)?)\s+" + // Match the type
            @"(?<name>\w+)" + // Match the name
            @"(?:\s*=\s*(?<default_value>.+))?" // Match the default value, if any
        );

        var match = pattern.Match(param.Trim());

        if (!match.Success)
        {
            throw new ArgumentException($"Invalid parameter signature: {param}");
        }

        var attributes = match.Groups[1].Value;
        var paramType = match.Groups["type"].Value;
        var paramName = match.Groups["name"].Value;
        var defaultValue = match.Groups["default_value"].Value;

        List<string> attributesList = null!;
        if (!string.IsNullOrEmpty(attributes))
        {
            attributesList = attributes.Split().ToList();
        }

        return new Tuple<List<string>, string, string, string>(attributesList, paramType, paramName, defaultValue);
    }

    public string ToJson()
    {
        return JsonConvert.SerializeObject(this, Formatting.Indented);
    }

    public override string ToString()
    {
        if (!string.IsNullOrEmpty(DefaultValue))
        {
            return $"{ParamType} {ParamName} = {DefaultValue}";
        }
        else
        {
            return $"{ParamType} {ParamName}";
        }
    }
}