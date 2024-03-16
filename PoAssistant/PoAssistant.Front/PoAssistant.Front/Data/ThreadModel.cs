namespace PoAssistant.Front.Data;

public class ThreadModel : List<MessageModel>
{
    public void RemoveLastThreadMessageFlags() => this.ForEach(msg => msg.SetAsLNotLastThreadMessage());
}
