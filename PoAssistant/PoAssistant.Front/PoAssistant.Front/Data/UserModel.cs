namespace PoAssistant.Front.Data;

public record User
{
    public User(string username, string password, int? userId = null)
    {
        UserId = userId;
        Username = username;
        Password = password;
    }

    public int? UserId { get; init; }
    public string Username { get; init; }
    public string Password { get; init; }
}

