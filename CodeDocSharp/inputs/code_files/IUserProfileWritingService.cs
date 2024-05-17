using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {
        /// <summary>
        /// 
        /// </summary>
        /// <param name="salesforceId"></param>
        /// <param name="code"></param>
        /// <param name="isCsvUpload"></param>
        /// <returns></returns>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

        /// <summary>
        /// Upload csv file payment reliability
        /// </summary>
        /// <param name="file"></param>
        /// <returns></returns>
        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

        /// <summary>
        /// Create user profile
        /// </summary>
        /// <param name="civilityId">Civility id</param>
        /// <param name="lastName">Last name</param>
        /// <param name="firstName">First name</param>
        /// <param name="birthDate">Birth date</param>
        /// <param name="email">Email</param>
        /// <param name="isOfficial">Is official</param>
        /// <param name="isTester">Is Tester</param>
        /// <param name="maidenName">Maiden name</param>
        /// <param name="createBy">Create by</param>
        /// <returns></returns>
        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}