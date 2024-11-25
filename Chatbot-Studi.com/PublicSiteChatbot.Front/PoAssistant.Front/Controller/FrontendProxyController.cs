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
    public FrontendProxyController(ConversationService ConversationService, UserStoryService userStoryService)
    {
        _ConversationService = ConversationService;
        _userStoryService = userStoryService;
    }

    private readonly ConversationService _ConversationService;
    private readonly UserStoryService _userStoryService;


    [HttpPost("metier-po/new-message/stream")]
    public async Task ReceiveMessageAsStream()
    {
        var buffer = new StringBuilder();
        _ConversationService.AddNewMessage();
        string? newWord = string.Empty;
        using (var reader = new StreamReader(Request.Body, Encoding.UTF8))
        {
            //StreamReaderExtensions.AddNewCharDelimiters(StreamHelper.NewLineForStream);
            while ((newWord = await reader.ReadWordAsync()) != null)
            {
                _ConversationService.DisplayStreamMessage(newWord);
            }
        }
        _ConversationService.EndsStreamMessage();
    }

    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
