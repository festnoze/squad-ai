using System.Text;

namespace PoAssistant.Front.Helpers;

public static class StreamReaderExtensions
{
    public static List<char> WordDelimiters = new List<char> { ' ' , '.' , ',' , '?' , '!', '-', '_' , '(', ')' };

    public static void AddNewCharDelimiters(params char[] newDelemiters)
    {
        foreach (char newDelemiter in newDelemiters)
            if (!WordDelimiters.Contains(newDelemiter))
                WordDelimiters.Add(newDelemiter);
    }

    public static async Task<string?> ReadWordAsync(this StreamReader reader)
    {
        if (reader == null)
            throw new ArgumentNullException(nameof(reader));

        var sb = new StringBuilder();
        char[] buffer = new char[1];
        bool foundDelimiter = false;

        while (!foundDelimiter && await reader.ReadAsync(buffer, 0, 1) > 0)
        {
            sb.Append(buffer[0]);
            if (WordDelimiters.IndexOf(buffer[0]) != -1)
                foundDelimiter = true;
        }

        return foundDelimiter ? sb.ToString() : null;
    }
}

