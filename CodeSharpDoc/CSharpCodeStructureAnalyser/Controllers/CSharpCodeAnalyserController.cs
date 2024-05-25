using CSharpCodeStructureAnalyser.Models;
using CSharpCodeStructureAnalyser.Services;
using Microsoft.AspNetCore.Mvc;

namespace CSharpCodeStructureAnalyser.Controllers;
[ApiController]
[Route("code-structure")]
public class CSharpCodeAnalyserController : ControllerBase
{
    public CSharpCodeAnalyserController()
    {
    }

    [HttpPost]
    [ActionName("GetAnalysedCSharpCodeStructure")]
    [Route("from-folder")]
    public IEnumerable<StructureDesc> GetAnalysedCSharpCodeFolder([FromBody] string folderPath)
    {
        return CSharpCodeAnalyserService.AnalyzeFolder(folderPath);
    }
}
