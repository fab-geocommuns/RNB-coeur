class DiffusionDatabaseView(APIView):
    def get(self, request):
        """Lists all databases in which ID-RNBs are published and available attributes"""
        databases = DiffusionDatabase.objects.all()
        serializer = DiffusionDatabaseSerializer(databases, many=True)
        return Response(serializer.data)


class OrganizationView(APIView):
    def get(self, request):
        """Lists all organization names"""
        organizations = Organization.objects.all()
        names = [org.name for org in organizations]
        return Response(names)
