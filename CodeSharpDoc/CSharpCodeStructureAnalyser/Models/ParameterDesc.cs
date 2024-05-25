using System.Text.RegularExpressions;
using Newtonsoft.Json;

namespace CSharpCodeStructureAnalyser.Models;

public record ParameterDesc : BaseDesc
{
    public string ParamName { get; set; }
    public string ParamType { get; set; }
    public bool HasDefaultValue { get; set; }
    public string DefaultValue { get; set; }
    public string Description { get; set; }
    public string ExtraInfos { get; set; }

    public ParameterDesc(string paramName, string paramType, bool hasDefaultValue = false, string defaultValue = null, string description = null, string extraInfos = null)
        : base(paramName)
    {
        ParamName = paramName;
        ParamType = paramType;
        HasDefaultValue = hasDefaultValue;
        DefaultValue = defaultValue;
        Description = description;
        ExtraInfos = extraInfos;
    }

    public static ParameterDesc FactoryParamDescFromCode(string paramCode)
    {
        string attributes = null;
        string defaultValue = null;
        bool hasAttributes = false;

        paramCode = paramCode.Trim();
        if (paramCode.StartsWith("["))
        {
            hasAttributes = true;
            int closingBracketIndex = paramCode.IndexOf(']');
            attributes = paramCode.Substring(1, closingBracketIndex - 1).Trim();
            paramCode = paramCode.Substring(closingBracketIndex + 1).Trim();
        }

        string[] paramParts = paramCode.Split(' ', StringSplitOptions.RemoveEmptyEntries);

        bool hasDefaultValue = paramCode.Contains("=");

        if (hasDefaultValue)
        {
            defaultValue = paramCode.Split('=')[1].Trim();
        }

        if (paramParts.Length != 2 + (hasDefaultValue ? 2 : 0))
        {
            throw new ArgumentException($"Invalid parameter code: {paramCode}");
        }

        string paramType = paramParts[0];
        string paramName = paramParts[1].Split('=')[0].Trim();

        return new ParameterDesc(paramName, paramType, hasDefaultValue, defaultValue, attributes);
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