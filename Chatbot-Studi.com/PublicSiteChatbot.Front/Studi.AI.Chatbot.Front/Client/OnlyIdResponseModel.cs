using System.Text.Json.Serialization;

public class OnlyIdResponseModel
{
    [JsonPropertyName("id")]
    public Guid Id { get; set; }
}