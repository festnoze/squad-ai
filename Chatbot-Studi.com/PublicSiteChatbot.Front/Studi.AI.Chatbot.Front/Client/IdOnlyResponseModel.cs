using System.Text.Json.Serialization;

public class IdOnlyResponseModel
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }
}