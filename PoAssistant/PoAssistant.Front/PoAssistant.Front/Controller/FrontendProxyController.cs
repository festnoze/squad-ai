using Microsoft.AspNetCore.Mvc;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;

namespace PoAssistant.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController
{
    public FrontendProxyController(ThreadService threadService)
    {
        _threadService = threadService;
    }

    private readonly ThreadService _threadService;

    [HttpPost("moa-moe/new-message")]
    public void NewMoaMoeMessage([FromBody] MessageModel newMessage)
    {
        _threadService.AddNewMessage(newMessage);
    }


    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
