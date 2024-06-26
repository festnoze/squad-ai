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
    [Route("analyse/from-folder")]
    public IEnumerable<StructureDesc> GetAnalysedCSharpCodeFolder([FromBody] List<string> filesPath)
    {
        return CSharpCodeAnalyserService.AnalyzeFiles(filesPath);
    }

    [HttpPost]
    [ActionName("AddSummariesToCSharpCodeFiles")]
    [Route("add-summaries/to-structures")]
    public void AddSummariesToCSharpCodeFiles([FromBody]List<StructSummariesInfos> structuresSummaries)
    {
        CodeEditionService.AddGeneratedSummariesToCodeFilesAndSave(structuresSummaries);
    }


    [HttpPost]
    [ActionName("AddSummariesToCSharpCodeFiles")]
    [Route("add-summaries/from-fake")]
    public void AddFake()
    {
        var tmp = 0;
    }
}
