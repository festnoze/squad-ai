namespace PoAssistant.Front.Data;

public class ApiSettings
{
    public string ApiHostUri { get; set; } = string.Empty;
}

public class ChatbotSettings
{
    public bool ShowBottomInputMessage { get; set; } = true;
    public bool ShowOngoingMessageInConversation { get; set; } = false;
    public bool ShowEmptyOngoingMessageInConversation { get; set; } = false;
}