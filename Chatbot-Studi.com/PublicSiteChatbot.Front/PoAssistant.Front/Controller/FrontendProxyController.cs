using Microsoft.AspNetCore.Mvc;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;
using System.Text;
using System.IO;
using PoAssistant.Front.Helpers;

namespace PoAssistant.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController : ControllerBase
{
    public FrontendProxyController(ConversationService threadService, UserStoryService userStoryService)
    {
        _threadService = threadService;
        _userStoryService = userStoryService;
    }

    private readonly ConversationService _threadService;
    private readonly UserStoryService _userStoryService;


    [HttpPost("metier-po/new-message/stream")]
    public async Task ReceiveMessageAsStream()
    {
        var buffer = new StringBuilder();
        _threadService.InitStreamMessage();
        string? newWord = string.Empty;
        using (var reader = new StreamReader(Request.Body, Encoding.UTF8))
        {
            //StreamReaderExtensions.AddNewCharDelimiters(StreamHelper.NewLineForStream);
            while ((newWord = await reader.ReadWordAsync()) != null)
            {
                _threadService.DisplayStreamMessage(newWord);
            }
        }
        _threadService.EndsStreamMessage();
    }

    [HttpPost("metier-po/update-last-message")]
    public void UpdateLastMetierPoMessage([FromBody] MessageModel newMessage)
    {
        _threadService.UpdateLastMessage(newMessage);
    }

    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
