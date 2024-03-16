using System.Text.Json;

namespace PoAssistant.Front.Data;

public class ThreadService
{
    public const string threadPath = "..\\..\\outputs\\";
    public const string endMoeTag = "[FIN_MOE_ASSIST]";
    private DateTime? latestFileModification = null;
    private ThreadModel? messages = null;

    public ThreadModel? GetMoeMoaExchange()
    {    
        //if (messages is not null)
        //    return messages;

        var jsonFilePath = Path.Combine(threadPath, "MOA_MOE_exchanges.json");
        var jsonData = File.ReadAllText(jsonFilePath);
        messages = JsonSerializer.Deserialize<ThreadModel>(jsonData);

        // Change end message of MOE & make it editable by user
        if (messages != null)
        {
            if (messages!.Last().Content.Contains(endMoeTag))
            {
                messages![messages.Count - 1] = messages!.Last() with { Content = "Merci. Je n'ai plus d'autres questions. Avez-vous d'autres points à aborder ? Sinon, cliquez sur 'Suivant'" };
                messages.Add(new MessageModel("MOA", "Ajouter des points à aborder avec le MOE si vous le souhaitez"));
            }

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }


        return messages;
    }
}
