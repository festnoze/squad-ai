namespace Studi.Api.Lms.Application.Services;

using MediatR;
using Studi.Api.Core.Exceptions.ErrorCodesLocalization.Base;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;
using Studi.Api.Lms.User.Domain.Aggregates.User.Queries;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Lms.User.Application.Decorators;
using Studi.Api.Lms.User.Application.Tools;
using Studi.Api.Lms.User.Application.Mapper;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;

[ScopedService(typeof(IUserProfileQueryingService))]
public class UserProfileQueryingService : IUserProfileQueryingService
{
    private readonly IMediator _mediator;
    private readonly ICustomWebResourceService _customWebResource;
    private readonly ICivilityService _civilityService;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Initialize key services and resources such as mediator, custom web resource, civility service, and user repository, ensuring none of the essential dependencies are null.
    /// </summary>
    /// <param name="mediator">The mediator instance used for sending and publishing messages in the application.</param>
    /// <param name="customWebResource">The service responsible for handling custom web resources.</param>
    /// <param name="civilityService">The service used to retrieve civility details.</param>
    /// <param name="userRepository">The repository interface for querying user profile information.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Check the payment reliability status for a specified user.
    /// </summary>
    /// <param name="userId">The identifier of the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns a Task indicating the payment reliability status of the specified user.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve basic information for a specified user after confirming their existence.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user is linked.</param>
    /// <param name="loadSchoolOptions">Optional parameter indicating whether to load additional school options. Default is false.</param>
    /// <returns>Returns a user's basic profile information.</returns>
    public async Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false)
    {
        var user = await _mediator.Send(new UserBaseQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.User.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        var userBasicInfoIto = await _mediator.Send(new UserBasicInfoQuery(userId));
        user!.SetBasicInfoInformations(BasicInfoModel.CreateExisting(userBasicInfoIto!));

        if (loadSchoolOptions)
        {
            var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
            Guard.Against.Null(userSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve user public information and related school options for a specified user. Check for the existence of user data and handle possible null values.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This helps in retrieving specific details related to the user's affiliation with the school.</param>
    /// <returns>Returns the user's public profile and associated school details.</returns>
    public async Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId)
    {
        var user = await _mediator.Send(new UserPublicInfoQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.PublicInfo.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString()); //TODO Localize

        var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        if (userSchoolOptions != null)
        {
            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));

            var userScoresItos = await _mediator.Send(new UserScoresQuery(userId, schoolId));
            user!.SetUserScoresModel(userScoresItos is null ? null : UserScoresModel.CreateExisting(userScoresItos!));

            var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
            Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);
            user!.SetTrainings(TrainingModel.CreateExistingList(userTrainingsItos!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve user registrations for courses within a specific school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This helps to filter or specify the context within which the user is being queried.</param>
    /// <returns>Returns user-specific course registration details.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve user details including personal information, ensuring validity through data validation checks.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns user profile and personal details as a validated user object.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve school options associated with a specific user and school, validating the data and returning a structured model.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user profile information and corresponding civility details.</param>
    /// <returns>Returns a list of validated school options for the specified user and school.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve the professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the profile information and corresponding civility details are to be retrieved.</param>
    /// <returns>Returns a list of professional experiences for the specified user.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of a user's profile based on a specific user ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile information and corresponding civility details are being retrieved.</param>
    /// <returns>Returns the review date of a user's profile.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the most recent study information for a specified user.
    /// </summary>
    /// <param name="userId">The user ID for which the profile information and corresponding civility details are to be retrieved.</param>
    /// <returns>Returns the most recent study information for the specified user.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve a list of contract types related to professional experiences.
    /// </summary>
    /// <returns>Returns a task containing a list of contract type strings.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve trainings associated with a specified user and school, ensuring data validity and returning an existing list of training models.
    /// </summary>
    /// <param name="userId">The unique identifier for a user. This ID is used to retrieve the user profile information along with the corresponding civility details.</param>
    /// <param name="schoolId">The unique identifier for a school. This ID helps to filter and contextualize the user's profile information within the specific school context.</param>
    /// <returns>Returns a list of training models for a specified user and school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve user notifications settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to filter the user's profile information and corresponding civility details.</param>
    /// <returns>Returns user notification settings for the specified user and school.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns the time zone information of the specified user.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve configuration information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This helps in retrieving school-specific information if needed.</param>
    /// <returns>Returns configuration details for a specified user and associated school.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the profile information and civility details are to be retrieved. This is a required parameter for identifying the user in the GetLastSessionInfosAsync method.</param>
    /// <param name="schoolId">The ID of the school associated with the user. This parameter helps to retrieve the specific user profile information and civility details in the context of the specified school in the GetLastSessionInfosAsync method.</param>
    /// <returns>Returns the last session information of a given user in a specified school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns the user's first connection date asynchronously.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the avatar URL for a specified user or return the default avatar URL if none is available.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the avatar URL for the specified user or a default if unavailable.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check if a user exists by their email address.
    /// </summary>
    /// <param name="email">The email address associated with the user profile to be retrieved. This parameter is used to locate and return the user's profile information and corresponding civility details.</param>
    /// <returns>Returns a boolean indicating whether a user exists with the given email address.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check if a user exists by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym or username of the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns whether a user exists by their pseudonym.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudonym for a user based on their given first name and last name.
    /// </summary>
    /// <param name="firstName">The first name of the user to retrieve profile information for.</param>
    /// <param name="lastName">The last name of the user to retrieve profile information for.</param>
    /// <returns>Returns a pseudonym based on the user's first and last names.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Retrieve the total number of user profiles based on specified filtering conditions.
    /// </summary>
    /// <param name="filtersCompositions">An optional collection of filter compositions that determine which profiles to count. Each filter composition can provide specific criteria for filtering the profiles.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve a list of user profiles based on specified filters and sorting parameters, including civility information.
    /// </summary>
    /// <param name="skip">The number of records to skip before starting to return results.</param>
    /// <param name="take">The number of records to return.</param>
    /// <param name="filtersCompositions">A collection of filters applied to the results. Null if no filters are specified.</param>
    /// <param name="sort">The sorting criteria for the results. Null if no specific sorting is required.</param>
    /// <returns>Returns a list of filtered and sorted user profiles.</returns>
    public async Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);
        PaginationTools.TransformSortFieldName(sort, fieldNameDecorator);

        var data = await _mediator.Send(new UserProfilesQuery(skip, take, filtersCompositions, sort));

        if(!data.Any())
            return Enumerable.Empty<IUserProfileRAto>();

        var civilities = this._civilityService.GetCivilities();
        return data.Select(q => ItoToAtoMapper.ToUserProfileRAto(q, civilities.FirstOrDefault(c => c.Name == q.Civility)?.Id));
    }


    /// <summary>
    /// Retrieve user profile information and corresponding civility details based on the provided user ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns user profile and civility details for the specified user ID.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}