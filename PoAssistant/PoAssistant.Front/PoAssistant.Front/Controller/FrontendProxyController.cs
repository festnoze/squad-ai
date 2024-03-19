using Microsoft.AspNetCore.Mvc;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;

namespace PoAssistant.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController
{
    public FrontendProxyController(ThreadMetierPoService threadService, UserStoryService userStoryService)
    {
        _threadService = threadService;
        _userStoryService = userStoryService;
    }

    private readonly ThreadMetierPoService _threadService;
    private readonly UserStoryService _userStoryService;

    [HttpPost("metier-po/new-message")]
    public void NewMetierPoMessage([FromBody] MessageModel newMessage)
    {
        _threadService.AddNewMessage(newMessage);
    }


    [HttpDelete("metier-po/delete-all")]
    public void DeleteMetierPoThread()
    {
        _threadService.DeleteMetierPoThread();
    }

    [HttpPost("po/us")]
    public void ReadyPoUserStory([FromBody] UserStoryModel userStory)
    {
        _threadService.EndMetierMetierExchange();
        _userStoryService.SetPoUserStory(userStory);
    }


    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
