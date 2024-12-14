namespace Studi.AI.Chatbot.Front.Client;

using Studi.AI.Chatbot.Front.Models;
using System.Text.Json.Serialization;

public class UserRequestModel
{
    [JsonPropertyName("user_id")]
    public Guid? UserId { get; set; }

    [JsonPropertyName("user_name")]
    public string UserName { get; set; } = "";

    [JsonPropertyName("IP")]
    public string IP { get; set; } = "";

    [JsonPropertyName("device_info")]
    public DeviceInfoRequestModel DeviceInfo { get; set; } = new();
}


public class DeviceInfoRequestModel
{
    [JsonPropertyName("user_agent")]
    public string UserAgent { get; set; } = string.Empty;

    [JsonPropertyName("platform")]
    public string Platform { get; set; } = string.Empty;

    [JsonPropertyName("app_version")]
    public string AppVersion { get; set; } = string.Empty;

    [JsonPropertyName("os")]
    public string Os { get; set; } = string.Empty;

    [JsonPropertyName("browser")]
    public string Browser { get; set; } = string.Empty;

    [JsonPropertyName("is_mobile")]
    public bool IsMobile { get; set; } = false;

    public static DeviceInfoRequestModel FromModel(DeviceInfoModel deviceInfoModel)
    {
        return new DeviceInfoRequestModel
        {
            UserAgent = deviceInfoModel.UserAgent,
            Platform = deviceInfoModel.Platform,
            AppVersion = deviceInfoModel.AppVersion,
            Os = deviceInfoModel.Os,
            Browser = deviceInfoModel.Browser,
            IsMobile = deviceInfoModel.IsMobile
        };
    }
}
