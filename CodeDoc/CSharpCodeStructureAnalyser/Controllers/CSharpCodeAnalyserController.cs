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
    public IEnumerable<StructureDesc> GetAnalysedCSharpCodeFolder([FromBody] List<string> filesPath, [FromQuery] bool includeActualSummaries)
    {
        return CSharpCodeAnalyserService.AnalyzeFiles(filesPath, includeActualSummaries);
    }

    [HttpPost]
    [ActionName("ReplaceExistingSummariesWithNewProvidedSummariesIntoCodeFiles")]
    [Route("replace-summaries/to-structures")]
    public void ReplaceExistingSummariesWithNewProvidedSummariesIntoCodeFiles([FromBody]List<StructSummariesInfos> structuresSummaries)
    {
        CodeEditionService.ReplaceExistingSummariesWithNewProvidedSummariesIntoCodeFiles(structuresSummaries);
    }
}
