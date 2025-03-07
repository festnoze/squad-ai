FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /
COPY ["CSharpCodeStructureAnalyser.csproj", "./"]
RUN dotnet restore "CSharpCodeStructureAnalyser.csproj"
COPY . .
RUN dotnet publish "CSharpCodeStructureAnalyser.csproj" -c Release -o /publish

FROM mcr.microsoft.com/dotnet/aspnet:7.0 AS runtime
WORKDIR /

ENV PORT=8213
ENV HOST_URI=0.0.0.0
ENV ASPNETCORE_URLS=http://${HOST_URI}:${PORT}
EXPOSE $PORT

COPY --from=build /publish .
ENTRYPOINT ["dotnet", "CSharpCodeStructureAnalyser.dll"]

