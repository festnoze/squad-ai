namespace PoAssistant.Front.Data;

using System.Text.Json.Serialization;
using System.Collections.Generic;

public class UserStoryModel
{
    [JsonPropertyName("us_desc")]
    public string Description { get; set; }

    [JsonPropertyName("use_cases")]
    public List<UseCaseModel> UseCases { get; set; }
}

public class UseCaseModel
{
    [JsonPropertyName("uc_desc")]
    public string Description { get; set; }

    [JsonPropertyName("acceptance_criteria")]
    public List<string> AcceptanceCriteria { get; set; }
}

//public record AcceptanceCriteriaModel
//{
//    public AcceptanceCriteriaModel(string description)
//    {
//        Description = description;
//    }

//    [JsonPropertyName("ac-desc")]
//    public string Description { get; init; }
//}
