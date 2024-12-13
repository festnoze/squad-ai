namespace Studi.AI.Chatbot.Front.Models;

public class ApiSettings
{
    public string ApiHostUri { get; set; } = string.Empty;
}

public class ChatbotSettings
{
    public bool ShowInputMessageAtBottom { get; set; } = true;
    public bool ShowOngoingMessageInConversation { get; set; } = false;
    public bool ShowEmptyOngoingMessageInConversation { get; set; } = false;
    public bool DoLoginOnStartup { get; set; } = false;
}