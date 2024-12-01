using Microsoft.VisualBasic;

namespace PoAssistant.Front.Data;

public class ConversationModel : List<MessageModel>
{
    public ConversationModel(Guid? id = null)
    {
        if (id is null)
            Id = Guid.NewGuid();
        else
            Id = id.Value;
    }

    public Guid Id { get; set; }
    public void RemoveLastConversationMessageFlags() => this.ForEach(msg => msg.SetAsNotLastConversationMessage());
    public void RemoveLastMessage() => this.RemoveAt(this.Count - 1);
    public bool IsLastMessageFromUser => this.Last().IsFromUser;
    public bool IsFirstUserMessage => this.Count(m => m.IsFromAI) == 1;

    public void AddMessage(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isStreaming = false)
    {
        AddMessage(new MessageModel(source, content, durationSeconds, isSavedMessage, isStreaming));
    }

    public void AddMessage(MessageModel newMessage)
    {
        this.Add(newMessage);
        RefreshLastMessageInConversation();
    }

    private void RefreshLastMessageInConversation()
    {
        if (this.Any())
        {
            this!.RemoveLastConversationMessageFlags();

            if (!this!.Last().IsFromAI)
                this?.Last().SetAsLastConversationMessage();
        }
    }
}
