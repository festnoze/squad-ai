using Newtonsoft.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Infrastructure;

public interface IUserRepository
{
    bool CheckUserExists(string username);
    User? GetUserByUsername(string username);
    void AddUser(User user);
    bool ValidateUserPassword(string username, string password);
}

public class UserRepository : IUserRepository
{
    private const string _usersJsonPath = "users_log_infos.json";
    private List<User> _users = new List<User>();

    public UserRepository()
    {
        LoadUsers();
    }

    private void LoadUsers()
    {
        if (File.Exists(_usersJsonPath))
        {
            string json = File.ReadAllText(_usersJsonPath);
            _users = JsonConvert.DeserializeObject<List<User>>(json) ?? throw new Exception("Unable to deserialize _users from Json file: got null");
        }
    }


    private void SaveUsersToJson()
    {
        string json = JsonConvert.SerializeObject(_users);
        File.WriteAllText(_usersJsonPath, json);
    }

    public void AddUser(User user)
    {
        _users.Add(user);
        SaveUsersToJson();
    }

    public bool CheckUserExists(string username)
    {
        return _users.Any(u => u.Username.Equals(username, StringComparison.OrdinalIgnoreCase));
    }

    public User? GetUserByUsername(string username)
    {
        return _users.FirstOrDefault(u => u.Username.Equals(username, StringComparison.OrdinalIgnoreCase));
    }

    public bool ValidateUserPassword(string username, string password)
    {
        var user = _users.FirstOrDefault(u => u.Username.Equals(username, StringComparison.OrdinalIgnoreCase));
        if (user != null)
        {
            return user.Password.Equals(password);
        }
        return false;
    }

}

