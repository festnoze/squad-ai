public class ChatService
{
    private List<Message> _messages = new List<Message>();

    public IEnumerable<Message> GetMessages() => _messages;

    public void AddMessage(string role, string content)
    {
        _messages.Add(new Message { Role = role, Content = content, Timestamp = DateTime.Now });
    }
}
