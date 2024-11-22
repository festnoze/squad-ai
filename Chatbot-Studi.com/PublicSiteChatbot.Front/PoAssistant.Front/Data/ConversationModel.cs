namespace PoAssistant.Front.Data;

public class ConversationModel : List<MessageModel>
{
    public ConversationModel()
    {}

    public ConversationModel(string source, string firstThreadMessage, bool isLastMessage)
    {
        this.Add(new MessageModel(source, firstThreadMessage, 0, false));
        if (isLastMessage)
            this.Last().SetAsLastThreadMessage();
    }

    public void RemoveLastThreadMessageFlags() => this.ForEach(msg => msg.SetAsLNotLastThreadMessage());
    public void RemoveLastMessage() => this.RemoveAt(this.Count - 1);
    public bool IsLastMessageFromSender => this[this.Count - 1].IsSender;
}
