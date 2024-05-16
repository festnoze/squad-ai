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
    /// Initialize the service by setting up necessary dependencies and checking for null values.
    /// </summary>
    /// <param name="mediator">Responsible for handling communication between components and managing requests or commands.</param>
    /// <param name="customWebResource">Service used to manage and retrieve custom web resources.</param>
    /// <param name="civilityService">Service used to manage and retrieve civility information about users.</param>
    /// <param name="userRepository">Repository interface for accessing and managing user data in the data store.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Check for non-negative user ID; retrieve payment reliability for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information are to be retrieved.</param>
    /// <returns>Returns the user's payment reliability status.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve basic information for a specified user, ensuring user existence and optionally loading school options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile and civility information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether or not to load additional school-related options. Default is false.</param>
    /// <returns>Returns basic user profile, including optional school-related options.</returns>
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
    /// Retrieve the public information and school options for a specified user.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile and public information should be retrieved.</param>
    /// <param name="schoolId">The identifier for the school that the user is associated with.</param>
    /// <returns>Returns the user's public information and associated school options asynchronously.</returns>
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
    /// Retrieve the first course registration details for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This parameter is used to specify which user's profile and civility information should be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school. This parameter helps to identify which school's registrations and related information are associated with the user.</param>
    /// <returns>Returns details of the user's first course registration for the specified school.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve personal information for a specified user. Check for null data and raise an error if the information is not found, then return the retrieved information.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for which the profile and civility information are to be retrieved.</param>
    /// <returns>Returns user's personal information.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve options available for a specified user and school if they exist.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is to be retrieved. This should be an integer.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile. This should be an integer.</param>
    /// <returns>Returns options for a specified user's school profile.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile along with their civility information is to be retrieved.</param>
    /// <returns>Returns a list of professional experiences for the specified user.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of a user profile specified by user ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being retrieved.</param>
    /// <returns>Returns the user's profile review date.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile and civility information is being retrieved. This is an integer value passed as a parameter to the method GetUserLastStudyInfosAsync.</param>
    /// <returns>Returns the latest study information for the specified user.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Get all contract types for professional experiences.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom to retrieve the profile and civility information.</param>
    /// <param name="token">The authorization token to validate the request.</param>
    /// <param name="includeDetails">A boolean flag indicating whether to include detailed information in the response.</param>
    /// <returns>Returns a list of contract types for professional experiences.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve the list of training sessions for a specific user and school, ensuring that the data is valid and exists.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile needs to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns a list of validated training sessions for a specific user and school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve notification settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile.</param>
    /// <returns>Returns notification settings for the specified user and school.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the profile and civility information are to be retrieved.</param>
    /// <returns>Returns the user's timezone information asynchronously.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve configuration information based on provided user and school identifiers.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The identifier for the school with which the user's profile information is associated.</param>
    /// <returns>Returns configuration information associated with the specified user and school.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information should be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns the last session info of a user at a specified school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the initial login date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is being retrieved.</param>
    /// <returns>Returns the date of the user's first login.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the avatar URL for a specified user, returning a default URL if the retrieved URL is empty or whitespace.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the profile and civility information is being retrieved.</param>
    /// <returns>Returns the avatar URL or a default URL.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check if a user exists based on the provided email.
    /// </summary>
    /// <param name="email">The email address of the user to be checked. This can be used to verify if a user profile exists along with their civility information if available.</param>
    /// <returns>Returns true if the user exists by email.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check if a user exists by a given pseudo.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user whose profile and civility information is to be retrieved in the ExistUserByPseudoAsync method.</param>
    /// <returns>Returns a task indicating whether the user exists by the given pseudo.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudonym based on the provided first and last names.
    /// </summary>
    /// <param name="firstName">The first name of the user whose profile and civility information need to be retrieved.</param>
    /// <param name="lastName">The last name of the user whose profile and civility information need to be retrieved.</param>
    /// <returns>Returns a pseudonym created from the provided first and last names.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Count the number of user profiles based on specified filter criteria.
    /// </summary>
    /// <param name="filtersCompositions">A collection of filter compositions that can be applied to the query. Each filter defines criteria to refine the search results for retrieving user profiles. This parameter is optional and defaults to null if not provided.</param>
    /// <returns>Returns the number of user profiles matching the specified filter criteria.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve user profiles with pagination, fields filtering, and sorting transformations, returning mapped user profiles with associated civilities information.
    /// </summary>
    /// <param name="skip">The number of profiles to skip before starting to collect the result set. Used for pagination.</param>
    /// <param name="take">The number of profiles to take in the result set. Defines the size of the page.</param>
    /// <param name="filtersCompositions">A collection of filter conditions combined to refine the search results. Optional parameter.</param>
    /// <param name="sort">The sorting criteria to order the user profiles. Optional parameter.</param>
    /// <returns>Returns a paginated list of filtered and sorted user profiles with civilities.</returns>
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
    /// Retrieve a user's profile along with their civility information if available.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is to be retrieved.</param>
    /// <returns>Returns user profile with optional civility details.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}