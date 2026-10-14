from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from django.utils.html import format_html
from .models import Category, Tag, Post, Comment, Like


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'display_post_count', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('name',)
    list_filter_submit = True
    list_fullwidth = True
    prepopulated_fields = {'slug': ('name',)}

    @display(description='Post Count')
    def display_post_count(self, obj):
        return obj.posts.filter(status='published').count()


@admin.register(Tag)
class TagAdmin(ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    ordering = ('name',)
    list_filter_submit = True
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Post)
class PostAdmin(ModelAdmin):
    list_display = (
        'title', 'author', 'category', 'status',
        'is_featured', 'display_thumbnail', 'views', 'created_at'
    )
    search_fields = ('title', 'content', 'excerpt')
    list_filter = ('status', 'is_featured', 'category')
    ordering = ('-created_at',)
    filter_horizontal = ('tags',)
    readonly_fields = ('views', 'created_at', 'updated_at', 'display_thumbnail')
    prepopulated_fields = {'slug': ('title',)}
    list_filter_submit = True
    list_fullwidth = True

    @display(description='Thumbnail')
    def display_thumbnail(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="width: 60px; height: 40px; object-fit: cover; border-radius: 4px;" />',
                obj.thumbnail.url
            )
        return "No Image"


@admin.register(Comment)
class CommentAdmin(ModelAdmin):
    list_display = ('author', 'post', 'display_content', 'is_approved', 'created_at')
    list_filter = ('is_approved',)
    search_fields = ('author__email', 'content', 'post__title')
    ordering = ('-created_at',)
    readonly_fields = ('author', 'post', 'parent', 'created_at', 'updated_at')
    list_filter_submit = True
    list_fullwidth = True
    actions = ['approve_comments', 'disapprove_comments']

    @display(description='Content')
    def display_content(self, obj):
        return obj.content[:60] + '...' if len(obj.content) > 60 else obj.content

    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = "Approve selected comments"

    def disapprove_comments(self, request, queryset):
        queryset.update(is_approved=False)
    disapprove_comments.short_description = "Disapprove selected comments"


@admin.register(Like)
class LikeAdmin(ModelAdmin):
    list_display = ('user', 'post', 'created_at')
    search_fields = ('user__email', 'post__title')
    ordering = ('-created_at',)
    readonly_fields = ('user', 'post', 'created_at')
    list_filter_submit = True
    list_fullwidth = True