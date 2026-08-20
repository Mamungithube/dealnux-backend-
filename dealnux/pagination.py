from rest_framework.pagination import PageNumberPagination
from .responses import success_response


class CustomPagination(PageNumberPagination):
    """
    Custom 10-item pagination with detailed pagination metadata.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_paginated_response(self, data):
        next_page_number = None
        if self.page.has_next():
            next_page_number = self.page.next_page_number()

        prev_page_number = None
        if self.page.has_previous():
            prev_page_number = self.page.previous_page_number()

        paginated_data = {
            "count": len(data),
            "results": data,
            "pagination": {
                "total_count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "has_next": self.page.has_next(),
                "has_previous": self.page.has_previous(),
                "next_page": next_page_number,
                "prev_page": prev_page_number,
            },
        }
        return success_response(paginated_data)


class StandardPagination(PageNumberPagination):
    """
    Standard 20-item pagination.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
