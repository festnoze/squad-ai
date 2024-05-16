using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update payment reliability for a user identified by a specified Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for the Salesforce record.</param>
    /// <param name="code">A specific code required by the endpoint to process the data.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the data is being uploaded via CSV.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Upload a CSV file that contains data related to payment reliability, and process the file to handle and extract the relevant information.
    /// </summary>
    /// <param name="file">The CSV file containing the payment reliability data to be uploaded.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date for a specified user's profile.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is being updated. It is an integer value.</param>
    /// <param name="reviewDateUtc">The date and time (in UTC) of the review. This is an optional parameter; if not specified, it defaults to null.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the user's profile picture using the specified user identifier and file reference.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">The globally unique identifier (GUID) of the file representing the new profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture of a specified user using a given file identifier.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">A GUID representing the unique identifier of the file containing the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update basic information for a specified user with provided LinkedIn URL and about me details.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional.</param>
    /// <param name="aboutMe">A brief description or information about the user. This parameter is optional.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update the visibility status of a user in the ranking for a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the tracking data is being sent.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking or not.</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the status of a user's appearance in the learner directory for a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose tracking data is being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Boolean value indicating whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Boolean value indicating whether the user is open to collaborate with others.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the actual location for a specified user, including the country code and timezone ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose location data is being updated.</param>
    /// <param name="countryCode">An optional string representing the ISO country code where the user is currently located. Can be null if the country code is unknown.</param>
    /// <param name="timezoneId">An optional string representing the time zone ID in which the user is located. Can be null if the timezone ID is unknown.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a new professional experience entry for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An object containing all the details of the user's professional experience, which is to be sent to the endpoint for tracking.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being tracked and sent to the endpoint.</param>
    /// <returns>Returns a Task indicating the asynchronous operation status.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a user's professional experience based on provided identifiers.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience that is to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience is being removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Replace the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="studyInfos">The study information to be sent to the specified endpoint.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update the notification registration details for a specified user and school, considering email and push subscription preferences.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="schoolId">The unique identifier for the school.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">A nullable boolean indicating whether the email subscription is active.</param>
    /// <param name="isPushSubscriptionActive">A nullable boolean indicating whether the push subscription is active.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user using the provided connection date in UTC.
    /// 
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This parameter is required and should be of type int.</param>
    /// <param name="connectionDateUtc">The optional date and time of the user's first connection in UTC. If not provided, it defaults to null and the current time will be used.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

    /// <summary>
    /// Create a user profile by retrieving the civility information, generating a pseudo if not provided, and sending the necessary data through a command.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the user's civility status.</param>
    /// <param name="lastName">The user's last name.</param>
    /// <param name="firstName">The user's first name.</param>
    /// <param name="birthDate">The user's date of birth.</param>
    /// <param name="email">The user's email address.</param>
    /// <param name="pseudo">The user's pseudonym or nickname, which may be null.</param>
    /// <param name="isOfficial">A boolean value indicating whether the user is an official member.</param>
    /// <param name="isTester">A boolean value indicating whether the user is a tester.</param>
    /// <param name="maidenName">The user's maiden name, which may be null.</param>
    /// <param name="createBy">The identifier of the creator of the user profile.</param>
    /// <returns>Returns a task representing the asynchronous operation of creating a user profile.</returns>

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}