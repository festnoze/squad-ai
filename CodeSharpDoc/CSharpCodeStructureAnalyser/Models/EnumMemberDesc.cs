using System.Text.Json.Serialization;

namespace CSharpCodeStructureAnalyser.Models;

public record EnumMemberDesc : BaseDesc
{
    [JsonPropertyName("member_name")]
    public string MemberName { get; set; }

    [JsonPropertyName("member_value")]
    public int MemberValue { get; set; }

    public EnumMemberDesc(string name, int value) : base(name)
    {
        MemberName = name;
        MemberValue = value;
    }
}

public record EnumMembersDesc
{
    [JsonPropertyName("members")]
    public List<EnumMemberDesc> Members { get; set; } = new List<EnumMemberDesc>();

    public EnumMembersDesc()
    {
        Members = new List<EnumMemberDesc>();
    }
}