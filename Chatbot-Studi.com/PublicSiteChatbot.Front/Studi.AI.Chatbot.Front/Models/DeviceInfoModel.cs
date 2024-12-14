namespace Studi.AI.Chatbot.Front.Models;

public record DeviceInfoModel
{
    public string UserAgent { get; set; } = string.Empty;
    public string Platform { get; set; } = string.Empty;
    public string AppVersion { get; set; } = string.Empty;
    public string Os { get; set; } = string.Empty;
    public string Browser { get; set; } = string.Empty;
    public bool IsMobile { get; set; } = false;
}
